"""
Skill (abstract base class) — Step 7.10
============================================
Hinglish: Skill = reusable Blender workflow — MULTIPLE tools ka
composition. Tool jaisa hi pattern (name, description, execute), lekin
Skill "HIGH LEVEL" hai — Tools "LOW LEVEL" hain (Step 7.13).

    Skill -> Planner-jaisa orchestration -> Tools -> BlenderBridge
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SkillResult:
    """Hinglish: ToolResult jaisa hi consistent shape — success/data/error."""
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
        # Dependency Injection — Skill khud BlenderBridge nahi chhuti,
        # sirf ToolCaller ke through jaati hai (jaisa Agent karta hai).
        self._tool_caller = tool_caller

    def can_handle(self, task: str) -> float:
        """
        Hinglish: Ye task kitna relevant hai is skill ke liye — 0.0
        se 1.0 tak score. Default implementation simple keyword match
        hai; concrete skills isko override kar sakti hain.
        """
        task_lower = task.lower()
        name_words = self.name.replace("_", " ").replace(".", " ").lower().split()
        matches = sum(1 for word in name_words if word in task_lower)
        return matches / len(name_words) if name_words else 0.0

    @abstractmethod
    def execute(self, context: Dict[str, Any]) -> SkillResult:
        raise NotImplementedError

    def validate(self, result: SkillResult) -> bool:
        """
        Hinglish: Default — sirf result.success dekhta hai. Concrete
        skills isko override karke Phase 4 Validators use kar sakti
        hain (Step 7.15).
        """
        return result.success