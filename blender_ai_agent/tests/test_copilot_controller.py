from . import _bpy_stub  # noqa: F401

import unittest
from dataclasses import dataclass
from typing import Optional

from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.copilot.messages import MessageRole


@dataclass
class FakeAgentResult:
    """Hinglish: RepairRunResult/AgentRunResult jaisa fake — Controller ko sirf ye shape chahiye."""
    reply_text: Optional[str]
    task_id: str = "fake_task"
    rolled_back: bool = False


class FakeAgent:
    """Hinglish: Controller ka test-double — duck typing verify karta hai."""

    def __init__(self, results):
        self._results = list(results)
        self._call_count = 0
        self.received_inputs = []

    def run(self, user_message):
        self.received_inputs.append(user_message)
        result = self._results[self._call_count]
        self._call_count += 1
        return result


class TestCopilotController(unittest.TestCase):

    def test_successful_submit_records_messages(self):
        agent = FakeAgent(results=[FakeAgentResult(reply_text="Cube created.")])
        controller = CopilotController(agent)

        result = controller.submit("Create a cube")

        self.assertTrue(result.success)
        self.assertEqual(result.reply_text, "Cube created.")

        messages = controller.session.get_messages()
        self.assertEqual(messages[0].role, MessageRole.USER)
        self.assertEqual(messages[1].role, MessageRole.ASSISTANT)

    def test_rolled_back_result_recorded_as_error(self):
        agent = FakeAgent(results=[
            FakeAgentResult(reply_text="Task failed: bad input", rolled_back=True)
        ])
        controller = CopilotController(agent)

        result = controller.submit("Do something invalid")

        self.assertFalse(result.success)
        messages = controller.session.get_messages()
        self.assertEqual(messages[-1].role, MessageRole.ERROR)

    def test_agent_receives_exact_user_input(self):
        agent = FakeAgent(results=[FakeAgentResult(reply_text="ok")])
        controller = CopilotController(agent)

        controller.submit("Move the cube to x=5")

        self.assertEqual(agent.received_inputs[0], "Move the cube to x=5")

    def test_cancel_marks_next_result_as_cancelled(self):
        agent = FakeAgent(results=[FakeAgentResult(reply_text="Cube created.")])
        controller = CopilotController(agent)

        controller.cancel()
        result = controller.submit("Create a cube")

        self.assertFalse(result.success)
        self.assertEqual(controller.session.get_messages()[-1].role, MessageRole.ERROR)

    def test_session_can_be_injected(self):
        from blender_ai_agent.copilot.session import CopilotSession

        custom_session = CopilotSession()
        agent = FakeAgent(results=[FakeAgentResult(reply_text="ok")])
        controller = CopilotController(agent, session=custom_session)

        self.assertIs(controller.session, custom_session)


if __name__ == "__main__":
    unittest.main()