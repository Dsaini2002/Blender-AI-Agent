from . import _bpy_stub  # noqa: F401

import math
import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.curve_tools import CreateCurveTool
from blender_ai_agent.tools.models import CreateCurveInput
from .fakes_ext import FakeBridge
from .test_lighting_tools import FakeRepeatedComposite


class TestCreateCurveInput(unittest.TestCase):

    def test_points_are_accepted_with_optional_radius(self):
        data = CreateCurveInput(name="C", points=[[0, 0, 0, 1.0], [0, 0, 1, 0.1]])
        self.assertEqual(data.points, [[0, 0, 0, 1.0], [0, 0, 1, 0.1]])
        self.assertEqual(data.curve_type, "BEZIER")

    def test_needs_points_or_preset(self):
        with self.assertRaises(ValueError):
            CreateCurveInput(name="C")

    def test_rejects_bad_points(self):
        for bad in ([[0, 0, 0]], [[0, 0], [1, 1]], [[0, 0, 0, 1, 5], [1, 1, 1]], "nonsense", 5):
            with self.assertRaises(ValueError, msg=str(bad)):
                CreateCurveInput(name="C", points=bad)

    def test_rejects_bad_values(self):
        two_points = [[0, 0, 0], [1, 0, 0]]
        for kwargs in ({"curve_type": "SPLINEY"}, {"thickness": -1}, {"thickness": 99}, {"resolution": 0},
                       {"segments": 2}, {"location": [0, 0]}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                CreateCurveInput(name="C", points=two_points, **kwargs)
        with self.assertRaises(ValueError):
            CreateCurveInput(name="C", preset="zigzag")

    def test_presets_generate_points(self):
        circle = CreateCurveInput(name="C", preset="circle", radius=2, segments=8)
        self.assertEqual(len(circle.points), 8)
        self.assertTrue(circle.closed)  # circle auto-closes
        for x, y, z in circle.points:
            self.assertAlmostEqual(math.hypot(x, y), 2.0)

        line = CreateCurveInput(name="C", preset="line", length=3)
        self.assertEqual(line.points, [[0.0, 0.0, 0.0], [3, 0.0, 0.0]])

        arc = CreateCurveInput(name="C", preset="arc", radius=1, angle_degrees=90, segments=4)
        self.assertEqual(len(arc.points), 5)
        self.assertAlmostEqual(arc.points[-1][0], 0.0, places=6)
        self.assertAlmostEqual(arc.points[-1][1], 1.0, places=6)

        spiral = CreateCurveInput(name="C", preset="spiral", radius=1, height=2, turns=2)
        self.assertAlmostEqual(spiral.points[-1][2], 2.0)
        self.assertGreater(len(spiral.points), 8)

        wave = CreateCurveInput(name="C", preset="wave", length=4, amplitude=0.5, waves=2)
        self.assertAlmostEqual(wave.points[-1][0], 4.0)
        self.assertLessEqual(max(abs(p[1]) for p in wave.points), 0.5 + 1e-9)

    def test_llm_style_inputs_and_proto_containers(self):
        data = CreateCurveInput(
            name="C", points=FakeRepeatedComposite([FakeRepeatedComposite([0.0, 0.0, 0.0]),
                                                    FakeRepeatedComposite([1.0, 0.0, 2.0])]),
            thickness="0.1", closed="false", resolution=12.0, location="[1, 2, 3]", curve_type="poly")
        self.assertEqual(data.points, [[0.0, 0.0, 0.0], [1.0, 0.0, 2.0]])
        self.assertEqual(data.thickness, 0.1)
        self.assertFalse(data.closed)
        self.assertEqual(data.resolution, 12)
        self.assertEqual(data.location, [1.0, 2.0, 3.0])
        self.assertEqual(data.curve_type, "POLY")


class TestCreateCurveTool(unittest.TestCase):

    def test_creates_curve_object_with_all_settings(self):
        bridge = FakeBridge()
        result = CreateCurveTool(bridge).execute({
            "name": "Flame", "points": [[0, 0, 0, 1], [0.1, 0, 0.5, 0.6], [0.2, 0, 1, 0.1]],
            "thickness": 0.1, "location": [1, 2, 0]})

        self.assertTrue(result.success, result.error)
        obj = bridge.get_object("Flame")
        self.assertEqual(obj.type, "CURVE")
        self.assertEqual(len(obj.curve_points), 3)
        self.assertEqual(obj.curve_points[2][3], 0.1)  # taper radius kept
        self.assertEqual(obj.thickness, 0.1)
        self.assertEqual(list(obj.location), [1, 2, 0])
        self.assertEqual(result.data["point_count"], 3)

    def test_preset_through_tool_and_name_collision(self):
        tool = CreateCurveTool(FakeBridge())
        self.assertTrue(tool.execute({"name": "Ring", "preset": "circle", "radius": 1}).success)
        second = tool.execute({"name": "Ring", "preset": "circle", "radius": 2})
        self.assertEqual(second.data["name"], "Ring.001")

    def test_invalid_input_is_a_clean_failure(self):
        result = CreateCurveTool(FakeBridge()).execute({"name": "C"})
        self.assertFalse(result.success)
        self.assertIn("points", result.error)

    def test_metadata(self):
        tool = CreateCurveTool(FakeBridge())
        self.assertEqual(tool.name, "curve.create")
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)


if __name__ == "__main__":
    unittest.main()