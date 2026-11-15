"""MemorySkillOrchestrator
=======================

    Task -> Memory Retrieval -> Skill Selection -> Personalized Execution
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from ..skills.base import SkillResult
from ..skills.registry import SkillRegistry
from .context import MemoryContextBuilder


@dataclass
class OrchestrationResult:
    skill_used: Optional[str]
    memory_applied: bool
    skill_result: Optional[SkillResult]


class MemorySkillOrchestrator:

    def __init__(self, skill_registry: SkillRegistry, memory_context_builder: MemoryContextBuilder):
        self._skill_registry = skill_registry
        self._memory_context_builder = memory_context_builder

    def handle_task(self, task: str, base_context: Dict[str, Any] = None) -> OrchestrationResult:
        skill = self._skill_registry.find_best_match(task)
        if skill is None:
            return OrchestrationResult(skill_used=None, memory_applied=False, skill_result=None)

        memory_context = self._memory_context_builder.build_context(task)
        merged_context = self._merge_context(base_context or {}, memory_context)

        result = skill.execute(merged_context)

        return OrchestrationResult(
            skill_used=skill.name,
            memory_applied=not memory_context.is_empty,
            skill_result=result,
        )

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _merge_context(self, base_context: Dict[str, Any], memory_context) -> Dict[str, Any]:
        merged = dict(base_context)
        merged["_memory_context"] = memory_context.render_text()
        return merged