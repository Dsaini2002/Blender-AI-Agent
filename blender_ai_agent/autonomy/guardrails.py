"""Guardrails"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class GuardrailViolation(str, Enum):
    MAX_STEPS_EXCEEDED = "MAX_STEPS_EXCEEDED"
    MAX_RETRIES_EXCEEDED = "MAX_RETRIES_EXCEEDED"
    MAX_RUNTIME_EXCEEDED = "MAX_RUNTIME_EXCEEDED"
    MAX_SCENE_CHANGES_EXCEEDED = "MAX_SCENE_CHANGES_EXCEEDED"


@dataclass
class GuardrailLimits:
    max_steps: int = 20
    max_retries: int = 3
    max_runtime_seconds: float = 300.0
    max_scene_changes: int = 100

    def __post_init__(self):
        if self.max_steps <= 0:
            raise ValueError("GuardrailLimits.max_steps must be positive")
        if self.max_retries < 0:
            raise ValueError("GuardrailLimits.max_retries must be non-negative")
        if self.max_runtime_seconds <= 0:
            raise ValueError("GuardrailLimits.max_runtime_seconds must be positive")


class GuardrailMonitor:

    def __init__(self, limits: GuardrailLimits = None):
        self._limits = limits or GuardrailLimits()
        self.steps_taken = 0
        self.retries_taken = 0
        self.scene_changes = 0

    def record_step(self) -> None:
        self.steps_taken += 1

    def record_retry(self) -> None:
        self.retries_taken += 1

    def record_scene_change(self) -> None:
        self.scene_changes += 1

    def check(self, elapsed_seconds: float = 0.0) -> Optional[GuardrailViolation]:
        if self.steps_taken > self._limits.max_steps:
            return GuardrailViolation.MAX_STEPS_EXCEEDED
        if self.retries_taken > self._limits.max_retries:
            return GuardrailViolation.MAX_RETRIES_EXCEEDED
        if elapsed_seconds > self._limits.max_runtime_seconds:
            return GuardrailViolation.MAX_RUNTIME_EXCEEDED
        if self.scene_changes > self._limits.max_scene_changes:
            return GuardrailViolation.MAX_SCENE_CHANGES_EXCEEDED
        return None

    @property
    def is_within_limits(self) -> bool:
        return self.check() is None