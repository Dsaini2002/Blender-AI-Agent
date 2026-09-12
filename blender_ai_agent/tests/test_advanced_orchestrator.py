from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.decomposer import TaskDecomposer
from blender_ai_agent.agent.advanced.orchestrator import AdvancedOrchestrator
from blender_ai_agent.agent.advanced.state import AgentState
from .fakes import FakeBridge


class TestAdvancedOrchestrator(unittest.TestCase):

    def test_all_subtasks_succeed_reaches_completed(self):
        bridge = FakeBridge()
        decomposer = TaskDecomposer()

        def always_succeed(subtask):
            return True

        orchestrator = AdvancedOrchestrator(bridge, decomposer, always_succeed)
        result = orchestrator.run("Create a product showcase.")

        self.assertTrue(result.success)
        self.assertEqual(result.final_state, AgentState.COMPLETED)
        self.assertEqual(len(result.completed_subtasks), 5)

    def test_checkpoint_created_after_each_successful_subtask(self):
        bridge = FakeBridge()
        decomposer = TaskDecomposer()

        orchestrator = AdvancedOrchestrator(bridge, decomposer, lambda st: True)
        result = orchestrator.run("Create a product showcase.")

        for record in result.completed_subtasks:
            self.assertTrue(record.checkpoint_name.startswith("subtask_"))

    def test_failure_midway_stops_and_rolls_back(self):
        bridge = FakeBridge()
        decomposer = TaskDecomposer()

        call_count = {"n": 0}

        def fail_on_third(subtask):
            call_count["n"] += 1
            return call_count["n"] < 3  # first 2 succeed, 3rd fails

        orchestrator = AdvancedOrchestrator(bridge, decomposer, fail_on_third)
        result = orchestrator.run("Create a product showcase.")

        self.assertFalse(result.success)
        self.assertEqual(result.final_state, AgentState.ROLLED_BACK)
        # Pehle 2 subtasks successful the, 3rd fail hua — record mein sab dikhna chahiye
        self.assertEqual(len(result.completed_subtasks), 3)
        self.assertTrue(result.completed_subtasks[0].success)
        self.assertTrue(result.completed_subtasks[1].success)
        self.assertFalse(result.completed_subtasks[2].success)

    def test_simple_instruction_runs_as_single_subtask(self):
        bridge = FakeBridge()
        decomposer = TaskDecomposer()

        orchestrator = AdvancedOrchestrator(bridge, decomposer, lambda st: True)
        result = orchestrator.run("Rename Cube to Hero.")

        self.assertTrue(result.success)
        self.assertEqual(len(result.completed_subtasks), 1)


if __name__ == "__main__":
    unittest.main()