from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.scene_tools import SceneInspectTool


class FakeInspector:
    def inspect(self):
        return {"scene": {"name": "FakeScene"}, "objects": []}


class TestSceneInspectTool(unittest.TestCase):

    def test_execute_returns_successful_tool_result(self):
        tool = SceneInspectTool(FakeInspector())
        result = tool.execute()

        self.assertTrue(result.success)
        self.assertEqual(result.data["scene"]["name"], "FakeScene")

    def test_tool_metadata(self):
        tool = SceneInspectTool(FakeInspector())
        self.assertEqual(tool.name, "scene.inspect")
        self.assertEqual(tool.permission, Permission.READ_ONLY)
        self.assertTrue(tool.description)


if __name__ == "__main__":
    unittest.main()