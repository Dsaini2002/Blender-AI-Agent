"""Validator (abstract base class)
===============================

    Tool response ≠ truth
    Blender scene = source of truth
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ValidationResult:
    valid: bool
    reasons: List[str] = field(default_factory=list)

    @staticmethod
    def ok() -> "ValidationResult":
        return ValidationResult(valid=True)

    @staticmethod
    def failed(*reasons: str) -> "ValidationResult":
        return ValidationResult(valid=False, reasons=list(reasons))


class Validator(ABC):

    @abstractmethod
    def validate(self, expected: Dict[str, Any], bridge) -> ValidationResult:
        raise NotImplementedError