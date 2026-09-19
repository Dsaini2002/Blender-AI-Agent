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

    def run(self, user_message, state=None):
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


class TestCopilotControllerSkillFastPath(unittest.TestCase):
    """Hinglish: 'house' jaisa request LLM ko chhue bina, seedha
    HouseBuilderSkill se handle ho jana chahiye."""

    def _build_controller(self):
        from blender_ai_agent.skills.builtins.house_builder import HouseBuilderSkill
        from blender_ai_agent.skills.registry import SkillRegistry
        from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool
        from blender_ai_agent.tools.object_tools import CreateObjectTool, TransformObjectTool
        from blender_ai_agent.tools.registry import ToolRegistry
        from blender_ai_agent.agent.tool_caller import ToolCaller
        from .fakes import FakeBridge

        bridge = FakeBridge()
        tool_registry = ToolRegistry()
        tool_registry.register(CreateObjectTool(bridge))
        tool_registry.register(TransformObjectTool(bridge))
        tool_registry.register(CreateMaterialTool(bridge))
        tool_registry.register(AssignMaterialTool(bridge))
        tool_caller = ToolCaller(tool_registry)

        skill_registry = SkillRegistry()
        skill_registry.register(HouseBuilderSkill(tool_caller))

        # Agent jaan-boojhkar KHAALI results deta hai — agar skill
        # fast-path kaam nahi karti, Agent.run() IndexError se crash
        # ho jayega, aur test fail hoga. Isse proof milta hai ki LLM
        # ko call hi nahi kiya gaya.
        agent = FakeAgent(results=[])
        controller = CopilotController(
            agent, skill_registry=skill_registry, tool_caller=tool_caller,
        )
        return controller, agent, bridge

    def test_house_request_bypasses_llm_and_builds_house(self):
        controller, agent, bridge = self._build_controller()

        result = controller.submit("Can you make a house for me?")

        self.assertTrue(result.success)
        self.assertEqual(agent.received_inputs, [])  # LLM never called
        self.assertIsNotNone(bridge.get_object("House_Walls"))
        self.assertIsNotNone(bridge.get_object("House_Roof"))
        self.assertIsNotNone(bridge.get_object("House_Door"))

    def test_unrelated_request_falls_back_to_agent(self):
        controller, agent, _ = self._build_controller()
        agent._results = [FakeAgentResult(reply_text="Cube created.")]

        result = controller.submit("Create a spinning cube")

        self.assertTrue(result.success)
        self.assertEqual(agent.received_inputs, ["Create a spinning cube"])


if __name__ == "__main__":
    unittest.main()