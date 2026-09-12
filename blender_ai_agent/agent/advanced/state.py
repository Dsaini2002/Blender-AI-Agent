"""
AdvancedAgentState — Step 9.35
===================================
Hinglish: Complex task ke poore lifecycle ka current stage track
karta hai — jaisa Phase 6 ka CopilotUIState tha, lekin advanced
agent ke internal execution ke liye.
"""

from enum import Enum


class AgentState(str, Enum):
    IDLE = "IDLE"
    PLANNING = "PLANNING"
    EXECUTING = "EXECUTING"
    OBSERVING = "OBSERVING"
    VALIDATING = "VALIDATING"
    REPAIRING = "REPAIRING"
    CHECKPOINTING = "CHECKPOINTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class AgentStateMachine:
    """
    Hinglish: State transitions ko track karta hai, aur INVALID
    transitions ko block karta hai (jaise IDLE se seedha COMPLETED
    jaana galat hai — planning/executing se guzarna chahiye).
    """

    _VALID_TRANSITIONS = {
        AgentState.IDLE: {AgentState.PLANNING},
        AgentState.PLANNING: {AgentState.EXECUTING, AgentState.FAILED},
        AgentState.EXECUTING: {AgentState.OBSERVING, AgentState.CHECKPOINTING, AgentState.FAILED},
        AgentState.OBSERVING: {AgentState.VALIDATING},
        AgentState.VALIDATING: {AgentState.COMPLETED, AgentState.REPAIRING, AgentState.CHECKPOINTING},
        AgentState.REPAIRING: {AgentState.EXECUTING, AgentState.ROLLED_BACK},
        AgentState.CHECKPOINTING: {AgentState.EXECUTING, AgentState.COMPLETED},
        AgentState.FAILED: {AgentState.ROLLED_BACK},
        AgentState.COMPLETED: set(),
        AgentState.ROLLED_BACK: set(),
    }

    def __init__(self):
        self._state = AgentState.IDLE
        self._history = [AgentState.IDLE]

    @property
    def current(self) -> AgentState:
        return self._state

    def transition_to(self, new_state: AgentState) -> None:
        allowed = self._VALID_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise ValueError(
                f"Invalid state transition: {self._state.value} -> {new_state.value}"
            )
        self._state = new_state
        self._history.append(new_state)

    @property
    def history(self):
        return list(self._history)

    @property
    def is_terminal(self) -> bool:
        return self._state in (AgentState.COMPLETED, AgentState.ROLLED_BACK)