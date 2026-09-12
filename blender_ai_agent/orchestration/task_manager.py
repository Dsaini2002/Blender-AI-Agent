"""
TaskManager — Step 11.17 / 11.18
=====================================
Hinglish: Long-running tasks ke liye state machine + pause/resume.
CheckpointManager (Phase 9) ka reuse — pause ka matlab hai "current
checkpoint save karo", resume ka matlab "wahin se aage badho".
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from ..agent.advanced.checkpoints import CheckpointManager


class TaskState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class InvalidTaskTransition(Exception):
    pass


@dataclass
class ManagedTask:
    task_id: str
    instruction: str
    state: TaskState = TaskState.QUEUED
    pause_checkpoint_name: str = ""


class TaskManager:

    _VALID_TRANSITIONS = {
        TaskState.QUEUED: {TaskState.RUNNING, TaskState.CANCELLED},
        TaskState.RUNNING: {TaskState.PAUSED, TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED},
        TaskState.PAUSED: {TaskState.RUNNING, TaskState.CANCELLED},
        TaskState.COMPLETED: set(),
        TaskState.FAILED: set(),
        TaskState.CANCELLED: set(),
    }

    def __init__(self, bridge):
        self._bridge = bridge
        self._checkpoint_manager = CheckpointManager(bridge)
        self._tasks: dict = {}

    def create_task(self, task_id: str, instruction: str) -> ManagedTask:
        task = ManagedTask(task_id=task_id, instruction=instruction)
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> ManagedTask:
        return self._tasks[task_id]

    def start(self, task_id: str) -> None:
        self._transition(task_id, TaskState.RUNNING)

    def pause(self, task_id: str) -> None:
        """Hinglish: Step 11.18 — pause ke waqt checkpoint save hota hai."""
        task = self.get_task(task_id)
        self._transition(task_id, TaskState.PAUSED)

        checkpoint = self._checkpoint_manager.create_checkpoint(f"pause_{task_id}")
        task.pause_checkpoint_name = checkpoint.name

    def resume(self, task_id: str) -> None:
        """Hinglish: Resume ke liye sirf state RUNNING mein wapas jaata hai — scene
        already checkpoint ki state mein hai (pause ke baad koi change nahi hua toh)."""
        self._transition(task_id, TaskState.RUNNING)

    def complete(self, task_id: str) -> None:
        self._transition(task_id, TaskState.COMPLETED)

    def fail(self, task_id: str) -> None:
        self._transition(task_id, TaskState.FAILED)

    def cancel(self, task_id: str) -> None:
        self._transition(task_id, TaskState.CANCELLED)

    def _transition(self, task_id: str, new_state: TaskState) -> None:
        task = self.get_task(task_id)
        allowed = self._VALID_TRANSITIONS.get(task.state, set())

        if new_state not in allowed:
            raise InvalidTaskTransition(f"Cannot transition task from {task.state.value} to {new_state.value}")

        task.state = new_state