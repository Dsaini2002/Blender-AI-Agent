"""Second 'create a football stadium' run (log 20261114_154756):
- 0.12 m pitch lines were registered as walkable paths, so the goals were pushed 1.1 m off the goal line
  and every check round reported them as 'blocking a path';
- rectangles drawn with curve.create came out with rounded corners;
- the penalty areas were drawn the wrong size in the wrong place;
- five fix rounds made no tool call at all;
- camera.create made 'Camera.001' while camera.set kept the old 'Camera' active;
- render.setup could not switch to Cycles."""

from . import _bpy_stub  # noqa: F401

import math
import unittest
from types import SimpleNamespace

from blender_ai_agent.tools import paths
from blender_ai_agent.tools.camera_tools import CreateCameraTool
from blender_ai_agent.tools.curve_tools import CreateCurveTool
from blender_ai_agent.tools.field_markings import (FieldMarkingsInput, FieldMarkingsTool, cricket_lines, football_lines,
                                                   markings_mesh)
from blender_ai_agent.tools.library_tools import LibraryPlaceTool
from blender_ai_agent.tools.ribbon import centre_line, has_sharp_corner
from .test_cricket_ground import LightBridge
from .test_park_regressions import ScaledBridge


class TestLinesAreNotPaths(unittest.TestCase):

    def setUp(self):
        paths.clear()

    def test_pitch_lines_never_push_the_goals(self):
        bridge = LightBridge()
        tool = CreateCurveTool(bridge)
        tool.execute({"name": "pitch_goal_area_right", "profile": "flat", "width": 0.12, "closed": True,
                      "points": [[0, -2.75, 0], [5.5, -2.75, 0], [5.5, 2.75, 0], [0, 2.75, 0]], "location": [47, 0, 0.02]})
        tool.execute({"name": "white_stripe", "profile": "flat", "width": 0.3, "points": [[40, 0, 0], [60, 0, 0]]})
        self.assertEqual(paths.live_paths(bridge), {})
        result = LibraryPlaceTool(bridge).execute({"model": "football_goal", "location": [52.5, 0, 0], "face_towards": [0, 0]})
        self.assertEqual(result.data["location"][:2], [52.5, 0.0])
        self.assertNotIn("moved_off_path", result.data)

    def test_real_paths_are_still_remembered(self):
        bridge = LightBridge()
        CreateCurveTool(bridge).execute({"name": "park_path", "profile": "flat", "width": 2.0,
                                         "points": [[-10, 0, 0], [10, 0, 0]]})
        self.assertIn("park_path", paths.live_paths(bridge))


class TestSharpCorners(unittest.TestCase):

    def test_box_keeps_its_corners_and_a_gentle_path_is_smoothed(self):
        box = [[0, 0, 0], [10, 0, 0], [10, 5, 0], [0, 5, 0]]
        self.assertTrue(has_sharp_corner(box, closed=True))
        line = centre_line(box, closed=True)
        self.assertEqual(len(line), 5)                                       # corners only, no bulging curve
        wiggle = [[0, 0, 0], [5, 1, 0], [10, 0, 0], [15, 1, 0]]
        self.assertFalse(has_sharp_corner(wiggle))
        self.assertGreater(len(centre_line(wiggle)), 4)

    def test_touchline_mesh_stays_rectangular(self):
        bridge = ScaledBridge()
        CreateCurveTool(bridge).execute({"name": "pitch_touchlines", "profile": "flat", "width": 0.12, "closed": True,
                                         "points": [[-52.5, -34, 0], [52.5, -34, 0], [52.5, 34, 0], [-52.5, 34, 0]]})
        verts = bridge.get_object("pitch_touchlines").fake_vertices
        xs = sorted({round(abs(v[0]), 2) for v in verts})
        self.assertTrue(all(x >= 52.4 for x in xs))                          # no vertex pulled inwards by smoothing


class TestFieldMarkings(unittest.TestCase):

    def test_football_dimensions(self):
        lines, spots, anchors = football_lines()
        penalty = lines[3]                                                   # first penalty area (right end)
        xs = [p[0] for p in penalty]
        ys = [p[1] for p in penalty]
        self.assertAlmostEqual(max(xs) - min(xs), 16.5)
        self.assertAlmostEqual(max(ys) - min(ys), 40.32)
        self.assertAlmostEqual(max(xs), 52.5)
        goal_area = lines[4]
        self.assertAlmostEqual(max(p[1] for p in goal_area) - min(p[1] for p in goal_area), 18.32)
        self.assertAlmostEqual(max(p[0] for p in goal_area) - min(p[0] for p in goal_area), 5.5)
        self.assertIn(((41.5, 0.0), 0.11), spots)
        arc = lines[5]
        for x, y in (arc[0], arc[-1]):                                       # the arc starts and ends on the box edge
            self.assertAlmostEqual(x, 36.0, places=3)
        self.assertEqual(anchors["goal_centres"], [[52.5, 0.0], [-52.5, 0.0]])

    def test_cricket_creases(self):
        lines, _, anchors = cricket_lines(boundary_radius=60)
        self.assertEqual(anchors["wicket_centres"], [[10.06, 0.0], [-10.06, 0.0]])
        popping = lines[1]
        self.assertAlmostEqual(popping[0][0], 10.06 - 1.22)
        self.assertAlmostEqual(max(math.hypot(*p) for p in lines[-1]), 60.0, places=3)

    def test_tool_builds_one_object_and_gives_positions(self):
        bridge = ScaledBridge()
        result = FieldMarkingsTool(bridge).execute({"sport": "football", "location": [0, 0, 0.02]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["name"], "football_lines")
        self.assertEqual(result.data["goal_centres"], [[52.5, 0.0], [-52.5, 0.0]])
        verts = bridge.get_object("football_lines").fake_vertices
        self.assertAlmostEqual(max(v[0] for v in verts), 52.5 + 0.06, places=2)
        self.assertLess(max(v[2] for v in verts) - min(v[2] for v in verts), 0.05)

    def test_turned_field_turns_its_anchors(self):
        result = FieldMarkingsTool(ScaledBridge()).execute({"sport": "tennis", "yaw_degrees": 90, "location": [5, 5, 0]})
        self.assertTrue(result.success, result.error)
        (x0, y0), (x1, y1) = result.data["net_line"]
        self.assertAlmostEqual(y0, 5.0, places=2)
        self.assertAlmostEqual(y1, 5.0, places=2)

    def test_mesh_is_lines_not_a_filled_field(self):
        verts, faces, _, width = markings_mesh(FieldMarkingsInput(sport="football"))
        self.assertEqual(width, 0.12)
        self.assertGreater(len(faces), 100)

    def test_unknown_sport_is_rejected(self):
        self.assertFalse(FieldMarkingsTool(ScaledBridge()).execute({"sport": "quidditch"}).success)


class TestCameraAndEngine(unittest.TestCase):

    def test_camera_create_reuses_and_activates(self):
        from .fakes import FakeBridge, FakeObject
        bridge = FakeBridge(objects=[FakeObject(name="Camera", type_="CAMERA")])
        result = CreateCameraTool(bridge).execute({"name": "Camera", "location": [75, -85, 45], "rotation": [0.84, 0, 0.78]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["name"], "Camera")
        self.assertTrue(result.data["active"])
        self.assertEqual([o.name for o in bridge.get_objects() if o.type == "CAMERA"], ["Camera"])
        self.assertEqual(list(bridge.get_object("Camera").location), [75, -85, 45])
        self.assertIs(bridge._active_camera, bridge.get_object("Camera"))


class TestIdleFixRounds(unittest.TestCase):

    def test_round_without_tool_calls_counts_as_no_progress(self):
        from .test_auto_verify import THREE, Case, StubLLM, critique  # noqa: F401
        import os
        import tempfile
        import time
        from blender_ai_agent.agent import post_verify as pv
        from blender_ai_agent.agent import self_correct as sc
        from blender_ai_agent.agent.tool_caller import ToolCaller
        from blender_ai_agent.copilot.controller import CopilotController
        from blender_ai_agent.copilot.step_progress import ProgressHistory, ProgressTracker
        from blender_ai_agent.inspectors.scene_inspector import SceneInspector
        from blender_ai_agent.tests.fakes import FakeObject
        from blender_ai_agent.tests.fakes_ext import FakeBridge
        from blender_ai_agent.tools.registry import ToolRegistry
        from blender_ai_agent.tools.scene_tools import SceneInspectTool

        bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(SceneInspectTool(SceneInspector(bridge)))
        prompts = []

        class IdleAgent:
            def run(self, text, state=None):
                prompts.append(text)
                if len(prompts) == 1:
                    for n in THREE:
                        bridge._objects.append(FakeObject(name=n, type_="MESH"))
                built = [SimpleNamespace(tool_call=SimpleNamespace(tool_name="object.create", arguments={}),
                                         tool_result=SimpleNamespace(success=True, data={}))] if len(prompts) == 1 else []
                return SimpleNamespace(reply_text="ok", task_id="t", rolled_back=False, executed_steps=built)

        tmp = tempfile.TemporaryDirectory()
        cfg = pv.VerifyConfig(mode="full", max_rounds=15, pass_score=10.0, fd_capture=False, stall_rounds=2,
                              output_dir=os.path.join(tmp.name, "c"), min_objects_for_vision=3, strict_review=False)
        scores = iter([critique(4, ["bad"]), critique(5, ["bad"]), critique(6, ["bad"]), critique(7, ["bad"])])
        llm = SimpleNamespace(generate=lambda *a, **k: next(scores))
        verifier = pv.PostRunVerifier(ToolCaller(registry), bridge, llm_factory=lambda c: llm, config_loader=lambda: cfg,
                                      builder_config_loader=lambda: sc.BuilderConfig(api_key="k"), sleep=lambda s: None)
        controller = CopilotController(IdleAgent(), tracker=ProgressTracker(history=ProgressHistory(
            path=os.path.join(tmp.name, "h.json")), clock=time.time), verifier=verifier)
        result = controller.submit("make a car")
        self.assertEqual(len(prompts), 3, result.reply_text)                                    # 1 build + 2 idle rounds, then stop
        self.assertIn("changed NOTHING", prompts[2])
        self.assertIn("made no changes in 2 rounds", result.reply_text)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
