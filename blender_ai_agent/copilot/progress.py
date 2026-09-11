"""
ProgressState — Step 6.7
============================
Hinglish: Multi-step task chalte waqt UI ko live status dikhana hai:

    ✓ object.create
    ✓ material.create
    → material.assign   (currently running)
    ○ modifier.add       (pending)

Isse Phase 4 ke ExecutionRecord (executed_steps) se build hota hai.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ProgressStep:
    tool_name: str
    status: StepStatus = StepStatus.PENDING

    @property
    def icon(self) -> str:
        """Hinglish: Spec ke example jaisa hi symbol — ✓ / → / ○ / ✗"""
        return {
            StepStatus.PENDING: "○",
            StepStatus.RUNNING: "→",
            StepStatus.COMPLETED: "✓",
            StepStatus.FAILED: "✗",
        }[self.status]


class ProgressState:

    def __init__(self):
        self.steps: List[ProgressStep] = []
        self.current_step_index: Optional[int] = None

    def set_plan(self, tool_names: List[str]) -> None:
        """Hinglish: Planner se plan milne ke baad, saare steps PENDING state mein set karo."""
        self.steps = [ProgressStep(tool_name=name) for name in tool_names]
        self.current_step_index = None

    def start_step(self, index: int) -> None:
        self.steps[index].status = StepStatus.RUNNING
        self.current_step_index = index

    def complete_step(self, index: int, success: bool) -> None:
        self.steps[index].status = StepStatus.COMPLETED if success else StepStatus.FAILED

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.COMPLETED)

    @property
    def total_count(self) -> int:
        return len(self.steps)

    @property
    def is_complete(self) -> bool:
        return self.total_count > 0 and all(
            s.status in (StepStatus.COMPLETED, StepStatus.FAILED) for s in self.steps
        )

    def render_text(self) -> str:
        """Hinglish: Spec ke example jaisa plain-text progress view."""
        return "\n".join(f"{step.icon} {step.tool_name}" for step in self.steps)