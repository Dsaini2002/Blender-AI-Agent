from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.scene_tools import SceneInspectTool


class FakeInspector:
    """SceneInspector ka fake — ek layer aur upar test karne ke liye."""

    def inspect(self):
        return {"scene": {"name": "FakeScene"}, "objects": []}


class TestSceneInspectTool(unittest.TestCase):

    def test_execute_delegates_to_inspector(self):
        tool = SceneInspectTool(FakeInspector())
        result = tool.execute()

        self.assertEqual(result["scene"]["name"], "FakeScene")

    def test_tool_metadata(self):
        tool = SceneInspectTool(FakeInspector())
        self.assertEqual(tool.name, "scene.inspect")
        self.assertTrue(tool.description)


if __name__ == "__main__":
    unittest.main()