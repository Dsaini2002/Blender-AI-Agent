"""'Create an indoor badminton court' (log 20261114_164047):
- only the first line of the multi-line prompt reached the agent (Ctrl+V into a one-line field);
- tennis lines were used for badminton (singles lines fell outside the court);
- object.delete(names=['Light']) failed and the repair guessed the newest object and deleted a WALL;
- mesh.lathe got `points` instead of `profile`, so every light fixture failed;
- the net was a thin tube - there was no net model."""

from . import _bpy_stub  # noqa: F401

import math
import unittest

from blender_ai_agent.agent.models import ToolCall
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.reliability.errors import ErrorCode, ToolError
from blender_ai_agent.reliability.recovery import RecoveryManager
from blender_ai_agent.tests.fakes import FakeBridge, FakeObject
from blender_ai_agent.tools.field_markings import (FieldMarkingsTool, badminton_lines, basketball_lines, tennis_lines,
                                                   volleyball_lines)
from blender_ai_agent.tools.library_tools import LibraryPlaceTool, load_library
from blender_ai_agent.tools.mesh_advanced_tools import LatheInput
from blender_ai_agent.tools.object_tools import DeleteObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from blender_ai_agent.ui.panel import recover_cut_paste
from .test_cricket_ground import LightBridge
from .test_park_regressions import ScaledBridge

PROMPT = """Create an indoor badminton court with real sizes:
- court 13.40 x 6.10 m (doubles), green synthetic floor
- net in the middle: 2 posts 1.55 m tall"""


class TestCutPaste(unittest.TestCase):

    def test_first_line_only_is_recovered_from_the_clipboard(self):
        self.assertEqual(recover_cut_paste("Create an indoor badminton court with real sizes:", PROMPT), PROMPT)

    def test_typed_prompt_is_left_alone(self):
        self.assertEqual(recover_cut_paste("make a red cube", PROMPT), "make a red cube")
        self.assertEqual(recover_cut_paste("make a red cube", "make a red cube"), "make a red cube")
        self.assertEqual(recover_cut_paste("make a red cube", ""), "make a red cube")


class TestDeleteSafety(unittest.TestCase):

    def test_delete_takes_a_list(self):
        bridge = FakeBridge(objects=[FakeObject(name="Light", type_="LIGHT"), FakeObject(name="wall_right")])
        result = DeleteObjectTool(bridge).execute({"names": ["Light"]})
        self.assertTrue(result.success, result.error)
        self.assertIsNone(bridge.get_object("Light"))
        self.assertIsNotNone(bridge.get_object("wall_right"))

    def test_several_names_and_missing_ones(self):
        bridge = FakeBridge(objects=[FakeObject(name="a"), FakeObject(name="b")])
        result = DeleteObjectTool(bridge).execute({"names": ["a", "b", "ghost"]})
        self.assertEqual(result.data["deleted"], ["a", "b"])
        self.assertEqual(result.data["not_found"], ["ghost"])

    def test_repair_never_guesses_what_to_delete(self):
        bridge = FakeBridge(objects=[FakeObject(name="wall_right")])
        registry = ToolRegistry()
        registry.register(DeleteObjectTool(bridge))
        registry.register(SceneInspectTool(SceneInspector(bridge)))
        recovery = RecoveryManager(ToolCaller(registry))
        error = ToolError(code=ErrorCode.MISSING_ARGUMENT, message="missing 'name'", recoverable=True)
        self.assertIsNone(recovery.attempt_recovery(ToolCall(tool_name="object.delete", arguments={"thing": ["Light"]}), error))
        self.assertIsNone(recovery.attempt_recovery(ToolCall(tool_name="object.delete", arguments={}), error))
        self.assertIsNotNone(bridge.get_object("wall_right"))


class TestLatheAlias(unittest.TestCase):

    def test_points_mean_profile(self):
        from blender_ai_agent.tools.mesh_advanced_tools import MeshLatheTool
        tool = MeshLatheTool(ScaledBridge())
        result = tool.execute({"name": "fixture", "points": [[0, 0], [0.4, 0], [0.3, 0.3], [0, 0.4]], "resolution": 16})
        self.assertTrue(result.success, result.error)


class TestCourtLines(unittest.TestCase):

    @staticmethod
    def extent(lines):
        xs = [p[0] for line in lines for p in line]
        ys = [p[1] for line in lines for p in line]
        return max(xs), max(ys)

    def test_badminton(self):
        lines, _, anchors = badminton_lines()
        self.assertEqual(self.extent(lines), (6.7, 3.05))                   # nothing outside the court
        xs = sorted({round(abs(line[0][0]), 2) for line in lines if line[0][0] == line[-1][0]})
        self.assertIn(1.98, xs)                                            # short service lines
        self.assertIn(5.94, xs)                                            # doubles long service lines
        singles = sorted({round(abs(line[0][1]), 2) for line in lines if line[0][1] == line[-1][1] and line[0][1]})
        self.assertIn(2.59, singles)
        self.assertEqual(anchors["net_model"], "badminton_net")

    def test_tennis_lines_stay_inside_a_smaller_court(self):
        lines, _, _ = tennis_lines(length=13.4, width=6.1)
        x, y = self.extent(lines)
        self.assertLessEqual(y, 3.05 + 1e-9)
        self.assertLessEqual(x, 6.7 + 1e-9)

    def test_volleyball_and_basketball(self):
        v_lines, _, v = volleyball_lines()
        self.assertEqual(self.extent(v_lines), (9.0, 4.5))
        self.assertEqual(v["net_model"], "volleyball_net")
        b_lines, _, b = basketball_lines()
        x, y = self.extent(b_lines)
        self.assertAlmostEqual(x, 14.0)
        self.assertAlmostEqual(y, 7.5)
        arc = b_lines[7]
        self.assertAlmostEqual(arc[0][1], 6.6, places=3)                   # meets the corner line
        self.assertAlmostEqual(min(p[0] for p in arc), 12.425 - 6.75, places=3)
        self.assertEqual(b["hoop_pole_spots"], [[15.0, 0.0], [-15.0, 0.0]])

    def test_tool_accepts_new_sports(self):
        for sport in ("badminton", "volleyball", "basketball"):
            result = FieldMarkingsTool(ScaledBridge()).execute({"sport": sport})
            self.assertTrue(result.success, f"{sport}: {result.error}")


class TestNetsAndHoop(unittest.TestCase):

    def test_badminton_net_size(self):
        spec = load_library()["badminton_net"]
        posts = [p for p in spec["parts"] if p["name"].startswith("post")]
        self.assertAlmostEqual(abs(posts[0]["offset"][1]) * 2, 6.10)
        self.assertAlmostEqual(posts[0]["scale"][2] * 2, 1.55)
        net = next(p for p in spec["parts"] if p["name"] == "net")
        zs = [v[2] for v in net["vertices"]]
        self.assertAlmostEqual(max(zs) - min(zs), 0.76)

    def test_all_nets_and_the_hoop_place(self):
        for model in ("badminton_net", "tennis_net", "volleyball_net", "basketball_hoop", "badminton net", "hoop"):
            result = LibraryPlaceTool(LightBridge()).execute({"model": model})
            self.assertTrue(result.success, f"{model}: {result.error}")

    def test_hoop_rim_is_regulation_and_faces_the_court(self):
        spec = load_library()["basketball_hoop"]
        rim = next(p for p in spec["parts"] if p["name"] == "rim")
        self.assertAlmostEqual(rim["offset"][2], 3.05)
        self.assertAlmostEqual(rim["offset"][1] - 1.0, 1.575)              # 1.575 m inside the baseline
        bridge = LightBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "basketball_hoop", "location": [15, 0, 0], "face_towards": [0, 0]})
        yaw = math.radians(result.data["yaw_degrees"])
        front = (-math.sin(yaw), math.cos(yaw))
        self.assertAlmostEqual(front[0], -1.0, places=6)


if __name__ == "__main__":
    unittest.main()
