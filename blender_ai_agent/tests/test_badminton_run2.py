"""Second badminton run (log 20261114_165852): lines painted green as if they were the court, no court
surface, racket built as a standing pole + rings, light/camera calls failed for a missing name, and a
Cycles render froze Blender for 40+ s."""

from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.camera_tools import CreateCameraTool, RenderPreviewTool
from blender_ai_agent.tools.field_markings import FieldMarkingsTool
from blender_ai_agent.tools.library_tools import LibraryPlaceTool, load_library
from blender_ai_agent.tools.lighting_tools import CreateLightTool
from .fakes import FakeBridge
from .test_cricket_ground import LightBridge
from .test_park_regressions import ScaledBridge


class TestCourtSurface(unittest.TestCase):

    def test_badminton_gets_a_green_surface_and_white_lines(self):
        bridge = ScaledBridge()
        result = FieldMarkingsTool(bridge).execute({"sport": "badminton", "name": "court", "location": [0, 0, 0.01]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["surface"], "court_surface")
        surface = bridge.get_object("court_surface")
        xs = [v[0] for v in surface.fake_vertices]
        self.assertAlmostEqual(max(xs), 6.7 + 1.0)                          # court + 1 m run-off
        self.assertLess(max(v[2] for v in surface.fake_vertices), 0.0)     # just under the lines
        lines_mat = bridge.get_material(bridge.get_object("court").material_name)
        surface_mat = bridge.get_material(surface.material_name)
        self.assertGreater(min(lines_mat.color[:3]), 0.9)                   # white
        self.assertGreater(surface_mat.color[1], surface_mat.color[0])      # green
        self.assertIn("do not recolour", result.data["note"])

    def test_football_has_no_surface_unless_asked(self):
        bridge = ScaledBridge()
        result = FieldMarkingsTool(bridge).execute({"sport": "football"})
        self.assertNotIn("surface", result.data)
        result = FieldMarkingsTool(bridge).execute({"sport": "tennis", "surface": False, "name": "t"})
        self.assertNotIn("surface", result.data)

    def test_custom_surface_colour(self):
        bridge = ScaledBridge()
        result = FieldMarkingsTool(bridge).execute({"sport": "badminton", "name": "c", "surface_color": [0.8, 0.1, 0.1]})
        mat = bridge.get_material(bridge.get_object(result.data["surface"]).material_name)
        self.assertGreater(mat.color[0], 0.7)


class TestRacketAndShuttle(unittest.TestCase):

    def test_models_lie_on_the_floor_at_real_size(self):
        lib = load_library()
        self.assertAlmostEqual(lib["badminton_racket"]["size"][0], 0.67, places=2)
        self.assertLess(lib["badminton_racket"]["size"][2], 0.05)           # lying flat, not a standing pole
        self.assertAlmostEqual(lib["shuttlecock"]["size"][2], 0.088, places=3)
        for model in ("racket", "badminton racket", "shuttlecock", "birdie"):
            result = LibraryPlaceTool(LightBridge()).execute({"model": model, "location": [1, 4, 0]})
            self.assertTrue(result.success, f"{model}: {result.error}")


class TestDefaultNames(unittest.TestCase):

    def test_light_and_camera_without_a_name(self):
        bridge = FakeBridge()
        light = CreateLightTool(bridge).execute({"light_type": "AREA", "location": [0, 0, 6], "energy": 300, "size": 2})
        self.assertTrue(light.success, light.error)
        camera = CreateCameraTool(bridge).execute({"location": [9, -8, 5.5], "rotation": [0.95, 0, 0.8]})
        self.assertTrue(camera.success, camera.error)
        self.assertEqual(camera.data["name"], "Camera")


class TestFastPreview(unittest.TestCase):

    def test_preview_is_fast_unless_final(self):
        bridge = FakeBridge()
        RenderPreviewTool(bridge).execute({"filepath": "a.png"})
        self.assertTrue(bridge._last_render_fast)
        RenderPreviewTool(bridge).execute({"filepath": "a.png", "final": True})
        self.assertFalse(bridge._last_render_fast)


if __name__ == "__main__":
    unittest.main()
