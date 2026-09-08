from . import _bpy_stub  # noqa: F401  (bpy stub install karne ke liye)

import unittest

from blender_ai_agent.tools.base import Tool


class TestToolBase(unittest.TestCase):

    def test_cannot_instantiate_tool_directly(self):
        """Tool ek ABC hai — isko directly banana nahi chahiye."""
        with self.assertRaises(TypeError):
            Tool()

    def test_subclass_without_execute_fails(self):
        """execute() implement kiye bina subclass bhi instantiate nahi ho sakti."""

        class BrokenTool(Tool):
            name = "broken"

        with self.assertRaises(TypeError):
            BrokenTool()

    def test_valid_subclass_works(self):
        """Sahi se implement ki gayi Tool subclass instantiate honi chahiye."""

        class GoodTool(Tool):
            name = "good"

            def execute(self, input_data=None):
                return {"ok": True}

        tool = GoodTool()
        self.assertEqual(tool.execute(), {"ok": True})


if __name__ == "__main__":
    unittest.main()