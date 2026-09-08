from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.object_tools import CreateObjectTool, DeleteObjectTool
from .fakes import FakeBridge, FakeObject


class TestCreateObjectTool(unittest.TestCase):

    def test_create_object_success(self):
        bridge = FakeBridge()
        tool = CreateObjectTool(bridge)

        result = tool.execute({"name": "Cube"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["name"], "Cube")
        self.assertEqual(result.data["type"], "MESH")

    def test_create_object_with_custom_location(self):
        bridge = FakeBridge()
        tool = CreateObjectTool(bridge)

        result = tool.execute({"name": "Cube", "location": [1, 2, 3]})

        self.assertEqual(result.data["location"], [1, 2, 3])

    def test_create_object_actually_appears_in_bridge(self):
        bridge = FakeBridge()
        tool = CreateObjectTool(bridge)

        tool.execute({"name": "Sphere", "primitive": "SPHERE"})

        self.assertIsNotNone(bridge.get_object("Sphere"))

    def test_missing_name_fails_gracefully(self):
        bridge = FakeBridge()
        tool = CreateObjectTool(bridge)

        result = tool.execute({})

        self.assertFalse(result.success)

    def test_permission_is_safe_write(self):
        tool = CreateObjectTool(FakeBridge())
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)


class TestDeleteObjectTool(unittest.TestCase):

    def test_delete_existing_object(self):
        cube = FakeObject(name="Cube")
        bridge = FakeBridge(objects=[cube])
        tool = DeleteObjectTool(bridge)

        result = tool.execute({"name": "Cube"})

        self.assertTrue(result.success)
        self.assertIsNone(bridge.get_object("Cube"))

    def test_delete_missing_object_fails_gracefully(self):
        bridge = FakeBridge(objects=[])
        tool = DeleteObjectTool(bridge)

        result = tool.execute({"name": "DoesNotExist"})

        self.assertFalse(result.success)
        self.assertIn("not found", result.error)

    def test_permission_is_destructive(self):
        tool = DeleteObjectTool(FakeBridge())
        self.assertEqual(tool.permission, Permission.DESTRUCTIVE)


if __name__ == "__main__":
    unittest.main()