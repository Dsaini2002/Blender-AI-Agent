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

    def test_validate_converts_dict_to_typed_input(self):
        from dataclasses import dataclass

        @dataclass
        class SimpleInput:
            name: str

        class TypedTool(Tool):
            name = "typed.tool"
            input_model = SimpleInput

            def run(self, validated_input):
                return ToolResult.ok({"received_name": validated_input.name})

        tool = TypedTool()
        result = tool.execute({"name": "Cube"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["received_name"], "Cube")

    def test_validate_missing_field_fails_gracefully(self):
        from dataclasses import dataclass

        @dataclass
        class SimpleInput:
            name: str

        class TypedTool(Tool):
            name = "typed.tool"
            input_model = SimpleInput

            def run(self, validated_input):
                return ToolResult.ok()

        tool = TypedTool()
        result = tool.execute({})  # 'name' missing

        self.assertFalse(result.success)
        self.assertIn("Invalid input", result.error)


if __name__ == "__main__":
    unittest.main()