from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.models import (
    CreateCameraInput, CreateMaterialInput, CreateObjectInput, ModifyMaterialInput, TransformObjectInput,
)
from .test_lighting_tools import FakeMapComposite, FakeRepeatedComposite


class TestVectorLeniency(unittest.TestCase):
    """Log: 'TransformObjectInput.location must have exactly 3 values [x, y, z]' stopped a whole task."""

    def test_transform_accepts_many_vector_formats(self):
        for value in ([1, 2, 3], (1, 2, 3), "1, 2, 3", "[1, 2, 3]", "(1 2 3)".replace(" ", ", "),
                      {"x": 1, "y": 2, "z": 3}, {"X": 1, "Y": 2, "Z": 3}, FakeRepeatedComposite([1, 2, 3]),
                      FakeMapComposite({"x": 1, "y": 2, "z": 3}), ["1", "2", "3"]):
            data = TransformObjectInput(name="A", location=value)
            self.assertEqual(data.location, [1, 2, 3], repr(value))

    def test_rotation_and_scale_too(self):
        data = TransformObjectInput(name="A", rotation="0, 0, 1.5", scale=FakeRepeatedComposite([2, 2, 2]))
        self.assertEqual(data.rotation, [0, 0, 1.5])
        self.assertEqual(data.scale, [2, 2, 2])

    def test_wrong_length_still_fails_and_shows_what_was_received(self):
        for bad in ([1, 2], [1, 2, 3, 4], "1, 2", {"x": 1}, "nope", 5):
            with self.assertRaises(ValueError, msg=repr(bad)) as ctx:
                TransformObjectInput(name="A", location=bad)
            self.assertIn("must have exactly 3 values", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            TransformObjectInput(name="A", location=[1, 2])
        self.assertIn("(got [1, 2])", str(ctx.exception))

    def test_existing_rules_unchanged(self):
        with self.assertRaises(ValueError):
            TransformObjectInput(name="A")                       # nothing to change
        with self.assertRaises(ValueError):
            TransformObjectInput(name="", location=[0, 0, 0])

    def test_create_object_and_camera_use_the_same_leniency(self):
        self.assertEqual(CreateObjectInput(name="A", location="1, 2, 3").location, [1, 2, 3])
        self.assertEqual(CreateObjectInput(name="A").location, [0.0, 0.0, 0.0])
        with self.assertRaises(ValueError):
            CreateObjectInput(name="A", location=[1, 2])
        cam = CreateCameraInput(name="C", location={"x": 0, "y": -8, "z": 3}, rotation=FakeRepeatedComposite([1, 0, 0]))
        self.assertEqual(cam.location, [0, -8, 3])
        self.assertEqual(cam.rotation, [1, 0, 0])
        self.assertIsNone(CreateCameraInput(name="C").location)
        with self.assertRaises(ValueError):
            CreateCameraInput(name="C", rotation=[1, 2])


class TestMaterialColourLeniency(unittest.TestCase):
    """Log: material.create failed with 'expected sequence items of type float, not str'."""

    def test_the_exact_log_failure_string_numbers(self):
        data = CreateMaterialInput(name="Sofa", color=["0.35", "0.45", "0.65"])
        self.assertEqual(data.color, [0.35, 0.45, 0.65])
        self.assertTrue(all(isinstance(c, float) for c in data.color))

    def test_many_colour_formats_for_create_and_modify(self):
        for value, expected in (
            ([0.8, 0.2, 0.2], [0.8, 0.2, 0.2]),
            ([0.8, 0.2, 0.2, 1.0], [0.8, 0.2, 0.2, 1.0]),
            ("0.8, 0.2, 0.2", [0.8, 0.2, 0.2]),
            ("red", [1.0, 0.0, 0.0]),
            ("dark brown", None),                       # not a known name -> must fail clearly, below
            ({"r": 0.8, "g": 0.2, "b": 0.2}, [0.8, 0.2, 0.2]),
            ("#FF0000", [1.0, 0.0, 0.0]),
            ([255, 0, 0], [1.0, 0.0, 0.0]),             # 0-255 scale
            (FakeRepeatedComposite([0.8, 0.2, 0.2]), [0.8, 0.2, 0.2]),
        ):
            if expected is None:
                continue
            self.assertEqual(CreateMaterialInput(name="M", color=value).color, expected, repr(value))
            self.assertEqual(ModifyMaterialInput(name="M", color=value).color, expected, repr(value))

    def test_wrong_length_keeps_the_original_message(self):
        for cls in (CreateMaterialInput, ModifyMaterialInput):
            with self.assertRaises(ValueError) as ctx:
                cls(name="M", color=[1, 2])
            self.assertIn("must have 3 (RGB) or 4 (RGBA) values", str(ctx.exception))

    def test_unusable_colour_error_shows_what_was_received(self):
        with self.assertRaises(ValueError) as ctx:
            CreateMaterialInput(name="M", color={"weird": "thing"})
        self.assertIn("got {'weird': 'thing'}", str(ctx.exception))

    def test_no_colour_is_still_fine(self):
        self.assertIsNone(CreateMaterialInput(name="M").color)
        self.assertEqual(ModifyMaterialInput(name="M", roughness=0.3).color, None)

    def test_roughness_and_metallic_accept_strings(self):
        data = ModifyMaterialInput(name="M", roughness="0.3", metallic="1")
        self.assertEqual((data.roughness, data.metallic), (0.3, 1.0))
        for bad in ({"roughness": "rough"}, {"roughness": 1.5}, {"metallic": "-1"}):
            with self.assertRaises(ValueError, msg=str(bad)):
                ModifyMaterialInput(name="M", **bad)

    def test_through_the_real_tool_nothing_reaches_blender_as_a_string(self):
        from blender_ai_agent.tools.material_tools import CreateMaterialTool, ModifyMaterialTool
        from .fakes import FakeBridge

        bridge = FakeBridge()
        created = CreateMaterialTool(bridge).execute({"name": "Sofa", "color": ["0.35", "0.45", "0.65"]})
        self.assertTrue(created.success, created.error)
        self.assertTrue(all(isinstance(c, float) for c in bridge.get_material("Sofa").color))

        modified = ModifyMaterialTool(bridge).execute({"name": "Sofa", "color": "red", "roughness": "0.4"})
        self.assertTrue(modified.success, modified.error)
        self.assertEqual(bridge.get_material("Sofa").roughness, 0.4)



if __name__ == "__main__":
    unittest.main()