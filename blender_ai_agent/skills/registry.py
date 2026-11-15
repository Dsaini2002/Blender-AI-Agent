"""SkillRegistry"""

from typing import Dict, List

from .base import Skill


class SkillRegistry:

    def __init__(self):
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        if not skill.name:
            raise ValueError("Skill must have a non-empty 'name'.")
        if skill.name in self._skills:
            raise ValueError(f"Skill '{skill.name}' already registered.")
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise KeyError(f"Skill '{name}' not found in registry.")
        return self._skills[name]

    def list_skills(self) -> List[str]:
        return list(self._skills.keys())

    def find_best_match(self, task: str, min_score: float = 0.3) -> Skill:
        best_skill = None
        best_score = 0.0

        for skill in self._skills.values():
            score = skill.can_handle(task)
            if score > best_score:
                best_score = score
                best_skill = skill

        return best_skill if best_score >= min_score else None