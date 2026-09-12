"""
AdvancedOrchestrator — Step 9.20 / 9.21 / 9.22
====================================================
Hinglish: Phase 9 ka main integration point.

    Complex instruction -> TaskDecomposer -> TaskGraph (dependency order)
        -> har sub-task ke liye: checkpoint -> skill/tool execute -> observe
        -> agar fail: latest checkpoint tak rollback, poora restart nahi (Step 9.32)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .checkpoints import CheckpointManager
from .decomposer import SubTask, TaskDecomposer
from .state import AgentState, AgentStateMachine
from .task_graph import TaskGraph


@dataclass
class SubTaskExecutionRecord:
    subtask_id: str
    description: str
    success: bool
    checkpoint_name: str = ""


@dataclass
class AdvancedTaskResult:
    completed_subtasks: List[SubTaskExecutionRecord] = field(default_factory=list)
    final_state: AgentState = AgentState.IDLE
    stopped_at_subtask: str = ""

    @property
    def success(self) -> bool:
        return self.final_state == AgentState.COMPLETED


class AdvancedOrchestrator:

    def __init__(self, bridge, decomposer: TaskDecomposer, skill_executor):
        """
        Hinglish: `skill_executor` ek callable hai:
            skill_executor(subtask: SubTask) -> bool (success/failure)
        Ye orchestrator ko kisi specific Skill/Tool implementation se
        decouple karta hai — Dependency Injection.
        """
        self._bridge = bridge
        self._decomposer = decomposer
        self._skill_executor = skill_executor
        self._checkpoint_manager = CheckpointManager(bridge)
        self._state_machine = AgentStateMachine()

    def run(self, instruction: str) -> AdvancedTaskResult:
        self._state_machine.transition_to(AgentState.PLANNING)

        subtasks = self._decomposer.decompose(instruction)
        graph = TaskGraph(subtasks)
        ordered_subtasks = graph.execution_order()

        result = AdvancedTaskResult()

        self._state_machine.transition_to(AgentState.EXECUTING)

        for subtask in ordered_subtasks:
            success = self._execute_subtask(subtask, result)
            if not success:
                result.final_state = AgentState.ROLLED_BACK
                result.stopped_at_subtask = subtask.id
                self._recover(result)
                return result

        self._state_machine.transition_to(AgentState.CHECKPOINTING)
        self._checkpoint_manager.create_checkpoint("final")
        self._state_machine.transition_to(AgentState.COMPLETED)
        result.final_state = AgentState.COMPLETED

        return result

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _execute_subtask(self, subtask: SubTask, result: AdvancedTaskResult) -> bool:
        success = self._skill_executor(subtask)

        checkpoint_name = ""
        if success:
            checkpoint = self._checkpoint_manager.create_checkpoint(f"subtask_{subtask.id}")
            checkpoint_name = checkpoint.name

        result.completed_subtasks.append(SubTaskExecutionRecord(
            subtask_id=subtask.id,
            description=subtask.description,
            success=success,
            checkpoint_name=checkpoint_name,
        ))

        return success

    def _recover(self, result: AdvancedTaskResult) -> None:
        """Hinglish: Step 9.32 — poora restart nahi, sirf latest valid checkpoint tak."""
        self._state_machine.transition_to(AgentState.FAILED)
        if self._checkpoint_manager.list_checkpoints():
            self._checkpoint_manager.rollback_to_latest()
        self._state_machine.transition_to(AgentState.ROLLED_BACK)