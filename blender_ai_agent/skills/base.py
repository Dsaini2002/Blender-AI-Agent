"""Skill (abstract base class)"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SkillResult:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = None
    steps_completed: List[str] = field(default_factory=list)

    @staticmethod
    def ok(data: Dict[str, Any] = None, steps_completed: List[str] = None) -> "SkillResult":
        return SkillResult(success=True, data=data or {}, steps_completed=steps_completed or [])

    @staticmethod
    def fail(error: str, steps_completed: List[str] = None) -> "SkillResult":
        return SkillResult(success=False, error=error, steps_completed=steps_completed or [])


class Skill(ABC):
    name: str = ""
    description: str = ""

    def __init__(self, tool_caller):
        self._tool_caller = tool_caller

    def can_handle(self, task: str) -> float:
        task_lower = task.lower()
        name_words = self.name.replace("_", " ").replace(".", " ").lower().split()
        matches = sum(1 for word in name_words if word in task_lower)
        return matches / len(name_words) if name_words else 0.0
    def required_permissions(self, tool_registry) -> list:
        return []

    def has_destructive_operations(self, tool_registry) -> bool:
        from ..tools.base import Permission
        for tool_name in self.required_permissions(tool_registry):
            tool = tool_registry.get(tool_name)
            if tool.permission == Permission.DESTRUCTIVE:
                return True
        return False

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> SkillResult:
        raise NotImplementedError

    def validate(self, result: SkillResult) -> bool:
        return result.success