from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.session import CopilotSession
from blender_ai_agent.copilot.messages import MessageRole


class TestCopilotSession(unittest.TestCase):

    def test_starts_empty(self):
        session = CopilotSession()
        self.assertEqual(len(session), 0)
        self.assertIsNone(session.current_task_id)

    def test_add_user_message(self):
        session = CopilotSession()
        session.add_user_message("Create a cube")

        messages = session.get_messages()
        self.assertEqual(messages[0].role, MessageRole.USER)
        self.assertEqual(messages[0].content, "Create a cube")

    def test_add_assistant_message_with_metadata(self):
        session = CopilotSession()
        session.add_assistant_message("Done.", metadata={"tool": "object.create"})

        msg = session.get_messages()[0]
        self.assertEqual(msg.metadata["tool"], "object.create")

    def test_add_error_message(self):
        session = CopilotSession()
        session.add_error_message("Something failed.")

        self.assertEqual(session.get_messages()[0].role, MessageRole.ERROR)

    def test_clear_resets_session(self):
        session = CopilotSession()
        session.add_user_message("hi")
        session.current_task_id = "task_001"

        session.clear()

        self.assertEqual(len(session), 0)
        self.assertIsNone(session.current_task_id)

    def test_messages_preserve_order(self):
        session = CopilotSession()
        session.add_user_message("first")
        session.add_assistant_message("second")

        contents = [m.content for m in session.get_messages()]
        self.assertEqual(contents, ["first", "second"])


if __name__ == "__main__":
    unittest.main()