"""'create a football stadium' (log 20261114_150903):
- object.transform refused to size fresh 2 m cubes into 110 m stands (the import-scale guard was too wide);
- the stands ended up as plain boxes - there was no stepped-seating tool;
- goal posts were left as default 2 m cylinders;
- the centre circle failed because curve.create had no name;
- the floodlights blew the pitch out to white."""

from . import _bpy_stub  # noqa: F401

import math
import unittest

from blender_ai_agent.agent.scene_checks import geometry_problems
from blender_ai_agent.agent.tool_selection import select_tools
from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tools.curve_tools import CreateCurveTool
from blender_ai_agent.tools.grandstand import MeshGrandstandTool, grandstand_parts
from blender_ai_agent.tools.library_tools import LibraryPlaceTool, load_library
from blender_ai_agent.tools.object_tools import TransformObjectTool
from .test_cricket_ground import LightBridge
from .test_park_regressions import ScaledBridge


class TestScaleGuard(unittest.TestCase):

    def test_fresh_cube_can_become_a_110_m_stand(self):
        cube = FakeObject(name="stand_north")
        cube.fake_bbox = {"min": [-1, -1, -1], "max": [1, 1, 1]}
        result = TransformObjectTool(ScaledBridge(objects=[cube])).execute({"name": "stand_north", "scale": [55, 9, 6]})
        self.assertTrue(result.success, result.error)

    def test_import_scale_is_still_guarded(self):
        bench = FakeObject(name="Bench_01", scale=[0.01, 0.01, 0.01])
        bench.fake_bbox = {"min": [-98.6, -38.6, 0.0], "max": [98.6, 38.6, 55.0]}
        result = TransformObjectTool(ScaledBridge(objects=[bench])).execute({"name": "Bench_01", "scale": [1, 1, 1]})
        self.assertFalse(result.success)


class TestGrandstand(unittest.TestCase):

    def test_steps_climb_away_from_the_front(self):
        body, seats, roof, size = grandstand_parts(length=105, rows=20, row_depth=0.8, row_rise=0.4, roof=True)
        rows = body[:20]
        tops = [b[5] for b in rows]
        fronts = [b[2] for b in rows]
        self.assertEqual(tops, sorted(tops))
        self.assertEqual(fronts, sorted(fronts))
        self.assertAlmostEqual(rows[0][2], 0.0)                     # front edge on y = 0
        self.assertAlmostEqual(rows[0][1] - rows[0][0], 105.0)
        self.assertGreater(len(seats), 20)                         # seats split by aisles
        self.assertTrue(roof)
        self.assertAlmostEqual(size["depth"], 16.35, places=2)

    def test_tool_builds_body_seats_roof_and_faces_the_field(self):
        bridge = ScaledBridge()
        result = MeshGrandstandTool(bridge).execute({"name": "stand_north", "length": 105, "rows": 20, "roof": True,
                                                     "location": [0, 40, 0], "face_towards": [0, 0]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["objects"], ["stand_north", "stand_north_seats", "stand_north_roof"])
        yaw = math.radians(result.data["yaw_degrees"])
        front = (math.sin(yaw), -math.cos(yaw))                    # local -Y after the turn
        self.assertAlmostEqual(front[0], 0.0, places=6)
        self.assertAlmostEqual(front[1], -1.0, places=6)          # stand at y=+40 looks back towards y=0
        body = bridge.get_object("stand_north")
        ys = [v[1] for v in body.fake_vertices]
        self.assertAlmostEqual(min(ys), 0.0)
        self.assertGreater(max(ys), 15.0)

    def test_side_stand_turns_too(self):
        result = MeshGrandstandTool(ScaledBridge()).execute({"name": "stand_east", "length": 68, "location": [60, 0, 0],
                                                             "face_towards": [0, 0]})
        yaw = math.radians(result.data["yaw_degrees"])
        front = (math.sin(yaw), -math.cos(yaw))
        self.assertAlmostEqual(front[0], -1.0, places=6)

    def test_bad_sizes_are_rejected(self):
        tool = MeshGrandstandTool(ScaledBridge())
        for bad in ({"length": 1}, {"rows": 0}, {"row_rise": 5}):
            self.assertFalse(tool.execute(bad).success, bad)

    def test_tool_is_offered_for_stadium_requests_only(self):
        from blender_ai_agent.agent.models import ToolDefinition
        defs = [ToolDefinition(name="mesh.grandstand", description="", parameters={}),
                ToolDefinition(name="object.create", description="", parameters={})]
        self.assertEqual([d.name for d in select_tools(defs, "create a football stadium")],
                         ["mesh.grandstand", "object.create"])
        self.assertEqual([d.name for d in select_tools(defs, "make a red apple")], ["object.create"])


class TestGoalAndLines(unittest.TestCase):

    def test_goal_has_real_size(self):
        spec = load_library()["football_goal"]
        posts = [p for p in spec["parts"] if p["name"].startswith("post")]
        inner = (posts[1]["offset"][0] - posts[0]["offset"][0]) - 2 * posts[0]["scale"][0]
        self.assertAlmostEqual(inner, 7.32, places=2)
        self.assertAlmostEqual(2 * posts[0]["scale"][2], 2.44, places=2)
        bridge = LightBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "goal", "location": [-52.5, 0, 0], "face_towards": [0, 0]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["model"], "football_goal")
        yaw = math.radians(result.data["yaw_degrees"])
        mouth = (math.sin(yaw), -math.cos(yaw))
        self.assertAlmostEqual(mouth[0], 1.0, places=6)            # left goal opens towards +X (the pitch)

    def test_curve_without_a_name_still_works(self):
        result = CreateCurveTool(ScaledBridge()).execute({"preset": "circle", "radius": 9.15, "profile": "flat",
                                                          "width": 0.12, "location": [0, 0, 0.02]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["name"], "circle_line")

    def test_default_two_metre_goal_post_is_reported(self):
        post = FakeObject(name="goal_left_post_l", location=[-52.5, -3.66, 0.0])
        post.fake_bbox = {"min": [-1, -1, 0], "max": [1, 1, 2]}
        post.material_name = "white"
        problems = geometry_problems(ScaledBridge(objects=[post]), ["goal_left_post_l"])
        self.assertEqual(problems[0]["severity"], "high")
        self.assertIn("default 2 x 2 x 2 m primitive", problems[0]["issue"])

    def test_floodlight_is_not_blinding(self):
        light = load_library()["stadium_light"]["lights"][0]
        self.assertLessEqual(light["energy"], 80000)


if __name__ == "__main__":
    unittest.main()
