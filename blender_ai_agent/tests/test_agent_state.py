from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.state import AgentState, AgentStateMachine


class TestAgentStateMachine(unittest.TestCase):

    def test_starts_idle(self):
        machine = AgentStateMachine()
        self.assertEqual(machine.current, AgentState.IDLE)

    def test_valid_transition_succeeds(self):
        machine = AgentStateMachine()
        machine.transition_to(AgentState.PLANNING)
        self.assertEqual(machine.current, AgentState.PLANNING)

    def test_invalid_transition_raises(self):
        machine = AgentStateMachine()
        with self.assertRaises(ValueError):
            machine.transition_to(AgentState.COMPLETED)  # IDLE se seedha COMPLETED galat hai

    def test_full_success_path(self):
        machine = AgentStateMachine()
        machine.transition_to(AgentState.PLANNING)
        machine.transition_to(AgentState.EXECUTING)
        machine.transition_to(AgentState.OBSERVING)
        machine.transition_to(AgentState.VALIDATING)
        machine.transition_to(AgentState.COMPLETED)

        self.assertTrue(machine.is_terminal)

    def test_history_tracks_all_transitions(self):
        machine = AgentStateMachine()
        machine.transition_to(AgentState.PLANNING)
        machine.transition_to(AgentState.EXECUTING)

        self.assertEqual(machine.history, [AgentState.IDLE, AgentState.PLANNING, AgentState.EXECUTING])

    def test_failure_path_reaches_rolled_back(self):
        machine = AgentStateMachine()
        machine.transition_to(AgentState.PLANNING)
        machine.transition_to(AgentState.EXECUTING)
        machine.transition_to(AgentState.FAILED)
        machine.transition_to(AgentState.ROLLED_BACK)

        self.assertTrue(machine.is_terminal)


if __name__ == "__main__":
    unittest.main()