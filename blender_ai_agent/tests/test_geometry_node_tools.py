from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.geometry_node_tools import CreateGeometryNodesTool
from .fakes import FakeBridge, FakeObject


class TestCreateGeometryNodesTool(unittest.TestCase):

    def test_create_success(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        tool = CreateGeometryNodesTool(bridge)

        result = tool.execute({"object_name": "Hero", "node_group_name": "Scatter"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["node_group"], "Scatter")

    def test_missing_object_fails_gracefully(self):
        bridge = FakeBridge(objects=[])
        tool = CreateGeometryNodesTool(bridge)

        result = tool.execute({"object_name": "DoesNotExist", "node_group_name": "Scatter"})

        self.assertFalse(result.success)

    def test_empty_node_group_name_fails_validation(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        tool = CreateGeometryNodesTool(bridge)

        result = tool.execute({"object_name": "Hero", "node_group_name": ""})

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()