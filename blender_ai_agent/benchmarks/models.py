"""Benchmark models"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    EXPERT = "expert"


@dataclass
class BenchmarkTask:
    id: str
    instruction: str
    expected_state: Dict[str, Any] = field(default_factory=dict)
    validation_rules: List[str] = field(default_factory=list)
    category: str = "basic"
    difficulty: Difficulty = Difficulty.EASY
    timeout: int = 120  # seconds

    def __post_init__(self):
        if not self.id:
            raise ValueError("BenchmarkTask.id must not be empty")
        if not self.instruction:
            raise ValueError("BenchmarkTask.instruction must not be empty")


@dataclass
class ValidationResult:
    rule_id: str
    passed: bool
    expected: Any = None
    actual: Any = None
    message: str = ""

    @property
    def score(self) -> float:
        return 1.0 if self.passed else 0.0


@dataclass
class BenchmarkResult:
    task_id: str
    status: TaskStatus
    score: float
    validation_results: List[ValidationResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration: float = 0.0
    tool_calls: int = 0
    retries: int = 0
    rollbacks: int = 0

    @property
    def success(self) -> bool:
        return self.status == TaskStatus.PASS

    @property
    def passed_rules(self) -> List[str]:
        return [r.rule_id for r in self.validation_results if r.passed]

    @property
    def failed_rules(self) -> List[str]:
        return [r.rule_id for r in self.validation_results if not r.passed]