from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.messages import CopilotMessage, MessageRole


class TestCopilotMessage(unittest.TestCase):

    def test_valid_message(self):
        msg = CopilotMessage(role=MessageRole.USER, content="Create a cube")
        self.assertEqual(msg.role, MessageRole.USER)

    def test_empty_content_raises_for_non_tool_role(self):
        with self.assertRaises(ValueError):
            CopilotMessage(role=MessageRole.ASSISTANT, content="")

    def test_tool_role_allows_empty_content(self):
        msg = CopilotMessage(role=MessageRole.TOOL, content="")
        self.assertEqual(msg.content, "")

    def test_metadata_defaults_to_empty_dict(self):
        msg = CopilotMessage(role=MessageRole.SYSTEM, content="init")
        self.assertEqual(msg.metadata, {})


if __name__ == "__main__":
    unittest.main()