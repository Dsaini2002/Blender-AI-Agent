from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.geometry_fix_tools import RecalculateNormalsTool, SeparateOverlapTool
from .fakes import FakeBridge, FakeObject


class TestRecalculateNormalsTool(unittest.TestCase):

    def test_fixes_flipped_normals(self):
        obj = FakeObject(name="Cube", flipped_normal_count=6)
        bridge = FakeBridge(objects=[obj])
        tool = RecalculateNormalsTool(bridge)

        result = tool.execute({"object_name": "Cube"})

        self.assertTrue(result.success)
        self.assertEqual(obj.flipped_normal_count, 0)

    def test_fails_for_missing_object(self):
        bridge = FakeBridge(objects=[])
        tool = RecalculateNormalsTool(bridge)

        result = tool.execute({"object_name": "Ghost"})

        self.assertFalse(result.success)

    def test_tool_metadata(self):
        tool = RecalculateNormalsTool(FakeBridge())
        self.assertEqual(tool.name, "geometry.recalculate_normals")
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)


class TestSeparateOverlapTool(unittest.TestCase):

    def test_moves_object_by_offset(self):
        obj = FakeObject(name="CubeA", location=[0.0, 0.0, 0.0])
        bridge = FakeBridge(objects=[obj])
        tool = SeparateOverlapTool(bridge)

        result = tool.execute({"object_name": "CubeA", "offset": [3.0, 0.0, 0.0]})

        self.assertTrue(result.success)
        self.assertEqual(list(obj.location), [3.0, 0.0, 0.0])

    def test_fails_for_missing_object(self):
        bridge = FakeBridge(objects=[])
        tool = SeparateOverlapTool(bridge)

        result = tool.execute({"object_name": "Ghost"})

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()
