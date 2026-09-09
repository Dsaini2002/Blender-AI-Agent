from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.agent.planner import Planner
from blender_ai_agent.agent.repair_loop import RepairableExecutionLoop
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.observability.logger import Logger
from blender_ai_agent.providers.mock_provider import MockProvider
from blender_ai_agent.reliability.recovery import RecoveryManager
from blender_ai_agent.reliability.tool_validators import ObjectExistsValidator, TransformValidator
from blender_ai_agent.tools.object_tools import CreateObjectTool, TransformObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge, FakeObject


def build_repair_loop(scripted_responses, objects=None, max_iterations=5):
    bridge = FakeBridge(objects=objects or [])

    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(TransformObjectTool(bridge))
    inspector = SceneInspector(bridge)
    registry.register(SceneInspectTool(inspector))

    tool_caller = ToolCaller(registry)
    context_manager = ContextManager(registry.get("scene.inspect"))
    provider = MockProvider(responses=scripted_responses)
    planner = Planner()
    recovery = RecoveryManager(tool_caller)
    logger = Logger()

    validators = {
        "object.create": ObjectExistsValidator(),
        "object.transform": TransformValidator(),
    }

    loop = RepairableExecutionLoop(
        model_provider=provider,
        tool_caller=tool_caller,
        context_manager=context_manager,
        planner=planner,
        bridge=bridge,
        recovery_manager=recovery,
        logger=logger,
        validators=validators,
        max_iterations=max_iterations,
    )
    return loop, bridge, logger


class TestSuccessfulTaskCommits(unittest.TestCase):

    def test_successful_task_logs_and_commits(self):
        loop, bridge, logger = build_repair_loop(scripted_responses=[
            ModelResponse(
                tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Cube"})],
                finish_reason="tool_calls",
            ),
            ModelResponse(content="Done."),
        ])

        result = loop.run("Create a cube")

        self.assertEqual(result.stopped_reason, "stop")
        self.assertFalse(result.rolled_back)
        self.assertIsNotNone(bridge.get_object("Cube"))

        event_names = [e.event for e in logger.get_events()]
        self.assertIn("task.start", event_names)
        self.assertIn("task.complete", event_names)


class TestSelfRepair(unittest.TestCase):
    """Exactly spec ka example: wrong object name, auto-corrected, retried, succeeds."""

    def test_wrong_object_name_gets_repaired_and_succeeds(self):
        loop, bridge, logger = build_repair_loop(
            objects=[FakeObject(name="Red_Cube", location=[0, 0, 0])],
            scripted_responses=[
                ModelResponse(
                    tool_calls=[ToolCall(
                        tool_name="object.transform",
                        arguments={"name": "RedCube", "location": [5, 0, 0]},  # galat naam
                    )],
                    finish_reason="tool_calls",
                ),
                ModelResponse(content="Moved the cube."),
            ],
        )

        result = loop.run("Move the red cube to x=5")

        self.assertEqual(result.stopped_reason, "stop")
        self.assertEqual(result.repairs_attempted, 1)
        self.assertTrue(result.executed_steps[-1].tool_result.success)
        self.assertEqual(bridge.get_object("Red_Cube").location, [5, 0, 0])

        error_events = [e.event for e in logger.get_events() if "repair" in e.event]
        self.assertTrue(len(error_events) > 0)


class TestRollbackOnUnrecoverableFailure(unittest.TestCase):

    def test_unrecoverable_failure_rolls_back_and_stops(self):
        loop, bridge, logger = build_repair_loop(
            objects=[FakeObject(name="Cube")],
            scripted_responses=[
                ModelResponse(
                    tool_calls=[
                        ToolCall(tool_name="object.create", arguments={"name": "Sphere"}),
                        ToolCall(tool_name="object.create", arguments={}),  # invalid — 'name' missing, unrecoverable
                    ],
                    finish_reason="tool_calls",
                ),
            ],
        )

        result = loop.run("Create sphere then something invalid")

        self.assertEqual(result.stopped_reason, "rollback")
        self.assertTrue(result.rolled_back)
        # Rollback ke baad Sphere bhi wapas nahi hona chahiye (transaction ke andar tha)
        self.assertIsNone(bridge.get_object("Sphere"))
        self.assertIsNotNone(bridge.get_object("Cube"))  # original object bacha hai


if __name__ == "__main__":
    unittest.main()