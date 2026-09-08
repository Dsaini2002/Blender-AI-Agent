from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Tool
from blender_ai_agent.tools.registry import ToolRegistry


class DummyTool(Tool):
    name = "dummy.tool"

    def execute(self, input_data=None):
        return {"result": "dummy"}


class TestToolRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()

    def test_register_and_get(self):
        tool = DummyTool()
        self.registry.register(tool)
        self.assertIs(self.registry.get("dummy.tool"), tool)

    def test_list_tools(self):
        self.registry.register(DummyTool())
        self.assertIn("dummy.tool", self.registry.list_tools())

    def test_duplicate_register_raises(self):
        self.registry.register(DummyTool())
        with self.assertRaises(ValueError):
            self.registry.register(DummyTool())

    def test_get_missing_tool_raises(self):
        with self.assertRaises(KeyError):
            self.registry.get("does.not.exist")


if __name__ == "__main__":
    unittest.main()