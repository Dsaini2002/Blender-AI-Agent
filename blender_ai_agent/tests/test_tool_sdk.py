from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.sdk.tools import create_tool
from blender_ai_agent.tools.base import Permission, ToolResult


class TestToolSDK(unittest.TestCase):

    def test_created_tool_has_correct_metadata(self):
        MyTool = create_tool(
            name="product.create_stand",
            description="Creates a display stand.",
            permission=Permission.SAFE_WRITE,
            fields={"height": float},
            run_fn=lambda self, inp: ToolResult.ok({"height": inp.height}),
        )

        tool = MyTool()

        self.assertEqual(tool.name, "product.create_stand")
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)

    def test_created_tool_executes_successfully(self):
        MyTool = create_tool(
            name="product.create_stand",
            description="Creates a display stand.",
            permission=Permission.SAFE_WRITE,
            fields={"height": float},
            run_fn=lambda self, inp: ToolResult.ok({"height": inp.height}),
        )

        tool = MyTool()
        result = tool.execute({"height": 1.5})

        self.assertTrue(result.success)
        self.assertEqual(result.data["height"], 1.5)

    def test_created_tool_validates_input(self):
        MyTool = create_tool(
            name="product.create_stand",
            description="test",
            permission=Permission.SAFE_WRITE,
            fields={"height": float},
            run_fn=lambda self, inp: ToolResult.ok(),
        )

        tool = MyTool()
        result = tool.execute({})  # 'height' missing

        self.assertFalse(result.success)

    def test_created_tool_handles_runtime_exception(self):
        def crashing_run(self, inp):
            raise RuntimeError("boom")

        MyTool = create_tool(
            name="test.crash",
            description="test",
            permission=Permission.SAFE_WRITE,
            fields={"x": int},
            run_fn=crashing_run,
        )

        tool = MyTool()
        result = tool.execute({"x": 1})

        self.assertFalse(result.success)
        self.assertIn("boom", result.error)


if __name__ == "__main__":
    unittest.main()