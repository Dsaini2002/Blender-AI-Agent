from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.agent.execution_loop import ExecutionLoop
from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.agent.planner import Planner
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.benchmarks.models import BenchmarkTask, TaskStatus
from blender_ai_agent.benchmarks.runner import BenchmarkRunner
from blender_ai_agent.benchmarks.validation_rules import ObjectExistsRule
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.providers.mock_provider import MockProvider
from blender_ai_agent.tools.object_tools import CreateObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge


def make_agent_factory(scripted_responses):
    def factory():
        bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(CreateObjectTool(bridge))
        inspector = SceneInspector(bridge)
        registry.register(SceneInspectTool(inspector))

        tool_caller = ToolCaller(registry)
        context_manager = ContextManager(registry.get("scene.inspect"))
        planner = Planner()
        provider = MockProvider(responses=scripted_responses)

        agent = ExecutionLoop(
            model_provider=provider,
            tool_caller=tool_caller,
            context_manager=context_manager,
            planner=planner,
        )
        return agent, bridge

    return factory


class TestBenchmarkRunner(unittest.TestCase):

    def test_successful_task_returns_pass(self):
        task = BenchmarkTask(id="t1", instruction="Create a cube named Hero.")

        agent_factory = make_agent_factory([
            ModelResponse(
                tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Hero"})],
                finish_reason="tool_calls",
            ),
            ModelResponse(content="Done."),
        ])

        def rules_factory(bridge):
            return [ObjectExistsRule("Hero")]

        result = BenchmarkRunner().run_task(task, agent_factory, rules_factory)

        self.assertEqual(result.status, TaskStatus.PASS)
        self.assertEqual(result.score, 1.0)

    def test_failed_task_returns_fail(self):
        task = BenchmarkTask(id="t2", instruction="Create a cube named Hero.")

        agent_factory = make_agent_factory([ModelResponse(content="I did nothing.")])

        def rules_factory(bridge):
            return [ObjectExistsRule("Hero")]

        result = BenchmarkRunner().run_task(task, agent_factory, rules_factory)

        self.assertEqual(result.status, TaskStatus.FAIL)
        self.assertEqual(result.score, 0.0)

    def test_agent_crash_returns_error_status(self):
        task = BenchmarkTask(id="t3", instruction="test")

        def crashing_agent_factory():
            raise RuntimeError("simulated crash")

        def rules_factory(bridge):
            return []

        result = BenchmarkRunner().run_task(task, crashing_agent_factory, rules_factory)

        self.assertEqual(result.status, TaskStatus.ERROR)
        self.assertTrue(len(result.errors) > 0)

    def test_run_suite_isolates_tasks(self):
        """Hinglish: Task 1 ka Hero object Task 2 ko affect nahi karna chahiye."""
        task1 = BenchmarkTask(id="t1", instruction="Create a cube named Hero.")
        task2 = BenchmarkTask(id="t2", instruction="Create a cube named Hero.")

        def agent_factory():
            return make_agent_factory([
                ModelResponse(
                    tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Hero"})],
                    finish_reason="tool_calls",
                ),
                ModelResponse(content="Done."),
            ])()

        def rules_factory(bridge):
            return [ObjectExistsRule("Hero")]

        results = BenchmarkRunner().run_suite([task1, task2], agent_factory, rules_factory)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.status == TaskStatus.PASS for r in results))


if __name__ == "__main__":
    unittest.main()