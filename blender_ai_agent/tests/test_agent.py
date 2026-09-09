from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.agent import Agent
from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.providers.mock_provider import MockProvider
from blender_ai_agent.tools.object_tools import CreateObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge


def build_agent(scripted_responses, objects=None):
    bridge = FakeBridge(objects=objects or [])

    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    inspector = SceneInspector(bridge)
    registry.register(SceneInspectTool(inspector))

    tool_caller = ToolCaller(registry)
    context_manager = ContextManager(registry.get("scene.inspect"))
    provider = MockProvider(responses=scripted_responses)

    agent = Agent(
        model_provider=provider,
        tool_caller=tool_caller,
        context_manager=context_manager,
    )
    return agent, bridge, provider


class TestAgentTextResponse(unittest.TestCase):

    def test_simple_text_reply(self):
        agent, _, _ = build_agent(
            scripted_responses=[ModelResponse(content="Hello! How can I help?")]
        )

        result = agent.run("Hi there")

        self.assertFalse(result.used_tool)
        self.assertEqual(result.reply_text, "Hello! How can I help?")


class TestAgentToolCall(unittest.TestCase):

    def test_tool_call_gets_executed(self):
        agent, bridge, _ = build_agent(
            scripted_responses=[
                ModelResponse(
                    tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Cube"})],
                    finish_reason="tool_calls",
                )
            ]
        )

        result = agent.run("Create a cube")

        self.assertTrue(result.used_tool)
        self.assertEqual(result.tool_call.tool_name, "object.create")
        self.assertTrue(result.tool_result.success)
        self.assertIsNotNone(bridge.get_object("Cube"))

    def test_unknown_tool_call_fails_gracefully(self):
        agent, _, _ = build_agent(
            scripted_responses=[
                ModelResponse(
                    tool_calls=[ToolCall(tool_name="does.not.exist", arguments={})],
                    finish_reason="tool_calls",
                )
            ]
        )

        result = agent.run("Do something weird")

        self.assertTrue(result.used_tool)
        self.assertFalse(result.tool_result.success)


class TestAgentRequestBuilding(unittest.TestCase):

    def test_provider_receives_tools_in_request(self):
        agent, _, provider = build_agent(
            scripted_responses=[ModelResponse(content="ok")]
        )

        agent.run("hello")

        sent_request = provider.received_requests[0]
        tool_names = {t.name for t in sent_request.tools}
        self.assertIn("object.create", tool_names)
        self.assertIn("scene.inspect", tool_names)

    def test_provider_receives_user_message(self):
        agent, _, provider = build_agent(
            scripted_responses=[ModelResponse(content="ok")]
        )

        agent.run("Create a red cube please")

        sent_request = provider.received_requests[0]
        self.assertEqual(sent_request.messages[0].content, "Create a red cube please")
        self.assertEqual(sent_request.messages[0].role, "user")


if __name__ == "__main__":
    unittest.main()