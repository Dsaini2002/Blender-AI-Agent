from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission, Tool, ToolResult


class TestToolBase(unittest.TestCase):

    def test_cannot_instantiate_tool_directly(self):
        with self.assertRaises(TypeError):
            Tool()

    def test_subclass_without_run_fails(self):
        class BrokenTool(Tool):
            name = "broken"

        with self.assertRaises(TypeError):
            BrokenTool()

    def test_valid_subclass_returns_tool_result(self):
        class GoodTool(Tool):
            name = "good"

            def run(self, validated_input):
                return ToolResult.ok({"ran": True})

        tool = GoodTool()
        result = tool.execute()

        self.assertIsInstance(result, ToolResult)
        self.assertTrue(result.success)
        self.assertEqual(result.data, {"ran": True})

    def test_run_exception_becomes_failed_result(self):
        """Tool crash na ho, error ToolResult mein wrap ho jaye."""

        class CrashingTool(Tool):
            name = "crasher"

            def run(self, validated_input):
                raise RuntimeError("boom")

        tool = CrashingTool()
        result = tool.execute()

        self.assertFalse(result.success)
        self.assertIn("boom", result.error)

    def test_default_permission_is_safe_write(self):
        class GoodTool(Tool):
            name = "good"

            def run(self, validated_input):
                return ToolResult.ok()

        self.assertEqual(GoodTool().permission, Permission.SAFE_WRITE)


if __name__ == "__main__":
    unittest.main()