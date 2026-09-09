from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.agent.execution_loop import ExecutionLoop
from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.agent.planner import Planner
from blender_ai_agent.agent.state import ConversationState
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.providers.mock_provider import MockProvider
from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool
from blender_ai_agent.tools.object_tools import CreateObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge


def build_loop(scripted_responses, objects=None, max_iterations=5):
    bridge = FakeBridge(objects=objects or [])

    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))
    inspector = SceneInspector(bridge)
    registry.register(SceneInspectTool(inspector))

    tool_caller = ToolCaller(registry)
    context_manager = ContextManager(registry.get("scene.inspect"))
    provider = MockProvider(responses=scripted_responses)
    planner = Planner()

    loop = ExecutionLoop(
        model_provider=provider,
        tool_caller=tool_caller,
        context_manager=context_manager,
        planner=planner,
        max_iterations=max_iterations,
    )
    return loop, bridge, provider


class TestSingleTurnTextReply(unittest.TestCase):

    def test_no_tool_calls_stops_immediately(self):
        loop, _, _ = build_loop(scripted_responses=[ModelResponse(content="Hi there!")])

        result = loop.run("Hello")

        self.assertEqual(result.reply_text, "Hi there!")
        self.assertEqual(result.tool_call_count, 0)
        self.assertEqual(result.turns_used, 1)
        self.assertEqual(result.stopped_reason, "stop")


class TestMultiStepSingleTurn(unittest.TestCase):
    """Step 3.8: Ek hi LLM response mein MULTIPLE tool calls."""

    def test_multiple_tool_calls_in_one_response_all_execute(self):
        loop, bridge, _ = build_loop(scripted_responses=[
            ModelResponse(
                tool_calls=[
                    ToolCall(tool_name="object.create", arguments={"name": "Cube"}),
                    ToolCall(tool_name="material.create", arguments={"name": "Red", "color": [1, 0, 0]}),
                ],
                finish_reason="tool_calls",
            ),
            ModelResponse(content="Done — created Cube and Red material."),
        ])

        result = loop.run("Create a cube and a red material")

        self.assertEqual(result.tool_call_count, 2)
        self.assertTrue(all(step.tool_result.success for step in result.executed_steps))
        self.assertIsNotNone(bridge.get_object("Cube"))
        self.assertEqual(result.reply_text, "Done — created Cube and Red material.")
        self.assertEqual(result.turns_used, 2)  # 1 tool turn + 1 final turn


class TestMultiTurnLoop(unittest.TestCase):
    """Step 3.7: LOOP khud kayi baar LLM ko call karta hai."""

    def test_sequential_dependent_tool_calls_across_turns(self):
        # Hinglish: 3 alag turns — jaise real Agent: create -> observe -> assign -> observe -> done
        loop, bridge, _ = build_loop(scripted_responses=[
            ModelResponse(
                tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Cube"})],
                finish_reason="tool_calls",
            ),
            ModelResponse(
                tool_calls=[ToolCall(tool_name="material.create", arguments={"name": "Red"})],
                finish_reason="tool_calls",
            ),
            ModelResponse(
                tool_calls=[ToolCall(tool_name="material.assign", arguments={
                    "object_name": "Cube", "material_name": "Red"
                })],
                finish_reason="tool_calls",
            ),
            ModelResponse(content="All done!"),
        ])

        result = loop.run("Create a red cube")

        self.assertEqual(result.tool_call_count, 3)
        self.assertEqual(result.turns_used, 4)
        self.assertEqual(result.reply_text, "All done!")
        self.assertEqual(result.stopped_reason, "stop")

    def test_max_iterations_prevents_infinite_loop(self):
        """Agar LLM kabhi 'final answer' na de, loop ruk jaana chahiye — crash nahi."""
        # Har baar ek tool call deta rahega — kabhi text nahi
        infinite_responses = [
            ModelResponse(
                tool_calls=[ToolCall(tool_name="object.create", arguments={"name": f"Cube{i}"})],
                finish_reason="tool_calls",
            )
            for i in range(10)
        ]
        loop, _, _ = build_loop(scripted_responses=infinite_responses, max_iterations=3)

        result = loop.run("Keep creating cubes")

        self.assertEqual(result.stopped_reason, "max_iterations_reached")
        self.assertEqual(result.turns_used, 3)
        self.assertEqual(result.tool_call_count, 3)  # 3 turns x 1 tool call


class TestConversationStatePersistence(unittest.TestCase):
    """Step 3.9: State object caller khud pass kar sakta hai, reuse ke liye."""

    def test_reusing_state_across_multiple_run_calls(self):
        loop, bridge, provider = build_loop(scripted_responses=[
            ModelResponse(
                tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Cube"})],
                finish_reason="tool_calls",
            ),
            ModelResponse(content="Cube created."),
            ModelResponse(content="Okay, noted — it's already red-ish in spirit."),
        ])

        state = ConversationState()

        first_result = loop.run("Create a cube", state=state)
        self.assertEqual(first_result.reply_text, "Cube created.")

        second_result = loop.run("Make it red", state=state)
        self.assertEqual(second_result.reply_text, "Okay, noted — it's already red-ish in spirit.")

        # Hinglish: State mein DONO conversations ki history honi chahiye
        all_messages = state.get_messages()
        user_messages = [m for m in all_messages if m.role == "user"]
        self.assertEqual(len(user_messages), 2)


if __name__ == "__main__":
    unittest.main()