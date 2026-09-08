from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.models import CreateObjectInput, DeleteObjectInput


class TestCreateObjectInput(unittest.TestCase):

    def test_defaults_applied(self):
        data = CreateObjectInput(name="Cube")
        self.assertEqual(data.object_type, "MESH")
        self.assertEqual(data.primitive, "CUBE")
        self.assertEqual(data.location, [0.0, 0.0, 0.0])

    def test_custom_location(self):
        data = CreateObjectInput(name="Cube", location=[1, 2, 3])
        self.assertEqual(data.location, [1, 2, 3])

    def test_empty_name_raises(self):
        with self.assertRaises(ValueError):
            CreateObjectInput(name="")

    def test_invalid_location_length_raises(self):
        with self.assertRaises(ValueError):
            CreateObjectInput(name="Cube", location=[1, 2])


class TestDeleteObjectInput(unittest.TestCase):

    def test_valid_name(self):
        data = DeleteObjectInput(name="Cube")
        self.assertEqual(data.name, "Cube")

    def test_empty_name_raises(self):
        with self.assertRaises(ValueError):
            DeleteObjectInput(name="")


if __name__ == "__main__":
    unittest.main()