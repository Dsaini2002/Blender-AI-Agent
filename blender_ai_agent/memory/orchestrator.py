"""
MemorySkillOrchestrator — Step 7.17
========================================
Hinglish: Phase 7 ka sabse important integration point.

    Task -> Memory Retrieval -> Skill Selection -> Personalized Execution

Spec ka exact example:
    User: "Create a product showcase."
    -> Memory: "User prefers dark studio"
    -> Skill: ProductShowcaseSkill
    -> Result: generic skill + user memory = personalized workflow
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
        # Dependency Injection — dono system yahan combine hote hain
        self._skill_registry = skill_registry
        self._memory_context_builder = memory_context_builder

    def handle_task(self, task: str, base_context: Dict[str, Any] = None) -> OrchestrationResult:
        """
        Hinglish:
          1. Task ke liye relevant memory dhoondo
          2. Task ke liye best-matching skill dhoondo
          3. Agar dono mile, memory ko skill context mein merge karke execute karo
          4. Koi skill na mile toh caller ko batao (Planner/normal flow use karega)
        """
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
        """
        Hinglish: Memory preferences ko skill context mein inject karta
        hai. Abhi simple rule: agar user_preference mein 'color' jaisa
        keyword mile, use extract karne ki koshish nahi karte (real
        NLP chahiye hoga) — bas memory summary ko context mein attach
        karte hain taaki skill (future mein) use kar sake.
        """
        merged = dict(base_context)
        merged["_memory_context"] = memory_context.render_text()
        return merged