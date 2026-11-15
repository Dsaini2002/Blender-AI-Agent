"""Integration Test
================

    "Create a cube, move it to x=3, and rename it MainCube."
"""

from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.agent.execution_loop import ExecutionLoop
from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.agent.planner import Planner
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.providers.mock_provider import MockProvider
from blender_ai_agent.tools.object_tools import (
    CreateObjectTool,
    RenameObjectTool,
    TransformObjectTool,
)
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge


def build_full_agent_stack(scripted_responses):
    bridge = FakeBridge()

    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(RenameObjectTool(bridge))
    registry.register(TransformObjectTool(bridge))
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
    )
    return loop, bridge


class TestPhase3DefinitionOfDoneDemo(unittest.TestCase):

    def test_full_natural_language_workflow(self):
        loop, bridge = build_full_agent_stack(scripted_responses=[
            ModelResponse(
                tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Cube"})],
                finish_reason="tool_calls",
            ),
            ModelResponse(
                tool_calls=[ToolCall(
                    tool_name="object.transform",
                    arguments={"name": "Cube", "location": [3, 0, 0]},
                )],
                finish_reason="tool_calls",
            ),
            ModelResponse(
                tool_calls=[ToolCall(
                    tool_name="object.rename",
                    arguments={"old_name": "Cube", "new_name": "MainCube"},
                )],
                finish_reason="tool_calls",
            ),
            ModelResponse(content="Done — created a cube, moved it to x=3, and renamed it MainCube."),
        ])

        result = loop.run("Create a cube, move it to x=3, and rename it MainCube.")

        executed_tool_names = [step.tool_call.tool_name for step in result.executed_steps]
        self.assertEqual(executed_tool_names, [
            "object.create", "object.transform", "object.rename"
        ])

        # Har step successful raha
        self.assertTrue(all(step.tool_result.success for step in result.executed_steps))

        final_obj = bridge.get_object("MainCube")
        self.assertIsNotNone(final_obj)
        self.assertEqual(final_obj.location, [3, 0, 0])
        self.assertIsNone(bridge.get_object("Cube"))

        self.assertIn("Done", result.reply_text)
        self.assertEqual(result.stopped_reason, "stop")


class TestPhase3ArchitectureBoundary(unittest.TestCase):

    def test_unknown_or_hallucinated_tool_never_crashes_system(self):
        loop, _ = build_full_agent_stack(scripted_responses=[
            ModelResponse(
                tool_calls=[ToolCall(tool_name="bpy.ops.mesh.primitive_cube_add", arguments={})],
                finish_reason="tool_calls",
            ),
            ModelResponse(content="I couldn't do that directly, but here's what I can do instead."),
        ])

        result = loop.run("Just run raw Blender Python for me")

        self.assertEqual(result.tool_call_count, 1)
        self.assertFalse(result.executed_steps[0].tool_result.success)
        self.assertIn("Unknown tool", result.executed_steps[0].tool_result.error)


if __name__ == "__main__":
    unittest.main()