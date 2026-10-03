from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.models import RetopologyInput
from blender_ai_agent.tools.retopology_tools import AnalyzeTopologyTool, RetopologyTool
from .fakes import FakeBridge, FakeObject


class TestRetopologyInput(unittest.TestCase):

    def test_defaults_and_auto_name(self):
        data = RetopologyInput(object_name="Statue")
        self.assertEqual(data.method, "QUADRIFLOW")
        self.assertEqual(data.new_name, "Statue_retopo")

    def test_method_is_case_insensitive(self):
        self.assertEqual(RetopologyInput(object_name="A", method="voxel").method, "VOXEL")

    def test_rejects_bad_method(self):
        with self.assertRaises(ValueError):
            RetopologyInput(object_name="A", method="MAGIC")

    def test_rejects_bad_numbers(self):
        for kwargs in ({"target_faces": 1}, {"target_faces": 2_000_000}, {"target_faces": 10.5},
                       {"target_faces": "lots"}, {"target_faces": True},
                       {"voxel_size": 0}, {"voxel_size": "x"}, {"decimate_ratio": 1.0}, {"decimate_ratio": 0}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                RetopologyInput(object_name="A", **kwargs)

    def test_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            RetopologyInput(object_name="")

    def test_accepts_llm_style_numbers(self):
        """Regression: Gemini sent target_faces as 500.0 / "500" and the task failed."""
        for value in (500, 500.0, "500", " 500 ", "500.0"):
            self.assertEqual(RetopologyInput(object_name="A", target_faces=value).target_faces, 500, value)
        self.assertIsInstance(RetopologyInput(object_name="A", target_faces=500.0).target_faces, int)
        self.assertEqual(RetopologyInput(object_name="A", voxel_size="0.1").voxel_size, 0.1)
        self.assertEqual(RetopologyInput(object_name="A", method="DECIMATE", decimate_ratio="0.25").decimate_ratio, 0.25)
        self.assertFalse(RetopologyInput(object_name="A", preserve_sharp="false").preserve_sharp)


class TestAnalyzeTopologyTool(unittest.TestCase):

    def test_reports_stats(self):
        obj = FakeObject(name="Rock", face_count=100, tri_count=40, pole_count=7)
        tool = AnalyzeTopologyTool(FakeBridge(objects=[obj]))

        result = tool.execute({"object_name": "Rock"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["face_count"], 100)
        self.assertEqual(result.data["quad_count"], 60)
        self.assertAlmostEqual(result.data["quad_ratio"], 0.6)
        self.assertEqual(result.data["pole_count"], 7)

    def test_fails_for_missing_or_non_mesh(self):
        light = FakeObject(name="Lamp", type_="LIGHT")
        tool = AnalyzeTopologyTool(FakeBridge(objects=[light]))
        self.assertFalse(tool.execute({"object_name": "Ghost"}).success)
        self.assertFalse(tool.execute({"object_name": "Lamp"}).success)

    def test_metadata(self):
        tool = AnalyzeTopologyTool(FakeBridge())
        self.assertEqual(tool.name, "retopology.analyze")
        self.assertEqual(tool.permission, Permission.READ_ONLY)


class TestRetopologyTool(unittest.TestCase):

    def _setup(self, **obj_kwargs):
        src = FakeObject(name="Statue", face_count=50000, tri_count=50000, pole_count=900, **obj_kwargs)
        bridge = FakeBridge(objects=[src])
        return src, bridge, RetopologyTool(bridge)

    def test_quadriflow_creates_copy_and_keeps_original(self):
        src, bridge, tool = self._setup()

        result = tool.execute({"object_name": "Statue", "method": "QUADRIFLOW", "target_faces": 1500})

        self.assertTrue(result.success)
        self.assertEqual(result.data["new_object"], "Statue_retopo")
        self.assertEqual(result.data["faces_before"], 50000)
        self.assertEqual(result.data["faces_after"], 1500)
        self.assertEqual(result.data["quad_ratio_after"], 1.0)
        # original untouched (only hidden), copy exists
        self.assertEqual(src.face_count, 50000)
        self.assertTrue(src.hidden)
        self.assertIsNotNone(bridge.get_object("Statue_retopo"))

    def test_decimate_reduces_by_ratio(self):
        _, _, tool = self._setup()
        result = tool.execute({"object_name": "Statue", "method": "DECIMATE", "decimate_ratio": 0.1})
        self.assertTrue(result.success)
        self.assertEqual(result.data["faces_after"], 5000)

    def test_voxel_method_succeeds(self):
        _, _, tool = self._setup()
        result = tool.execute({"object_name": "Statue", "method": "VOXEL", "voxel_size": 0.1})
        self.assertTrue(result.success)
        self.assertEqual(result.data["method"], "VOXEL")

    def test_tool_accepts_float_and_aliased_face_count(self):
        _, bridge, tool = self._setup()
        result = tool.execute({"object_name": "Statue", "method": "quadriflow", "target_faces": 500.0})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["faces_after"], 500)

        result = tool.execute({"object_name": "Statue", "target_face_count": "300"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["faces_after"], 300)

    def test_hide_original_false_keeps_it_visible(self):
        src, _, tool = self._setup()
        tool.execute({"object_name": "Statue", "hide_original": False})
        self.assertFalse(src.hidden)

    def test_name_collision_gets_suffix(self):
        _, bridge, tool = self._setup()
        tool.execute({"object_name": "Statue"})
        second = tool.execute({"object_name": "Statue"})
        self.assertEqual(second.data["new_object"], "Statue_retopo.001")

    def test_fails_for_missing_or_non_mesh(self):
        light = FakeObject(name="Lamp", type_="LIGHT")
        tool = RetopologyTool(FakeBridge(objects=[light]))
        self.assertFalse(tool.execute({"object_name": "Ghost"}).success)
        self.assertFalse(tool.execute({"object_name": "Lamp"}).success)

    def test_invalid_input_returns_failure_not_crash(self):
        _, _, tool = self._setup()
        result = tool.execute({"object_name": "Statue", "method": "MAGIC"})
        self.assertFalse(result.success)
        self.assertIn("method", result.error)

    def test_metadata(self):
        tool = RetopologyTool(FakeBridge())
        self.assertEqual(tool.name, "retopology.remesh")
        # Always works on a copy, so it is not DESTRUCTIVE
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)


if __name__ == "__main__":
    unittest.main()