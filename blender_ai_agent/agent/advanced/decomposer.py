"""
TaskDecomposer — Step 9.2
=============================
Hinglish: Complex, high-level instruction ko chhote, actionable
sub-tasks mein todta hai. Abhi ke liye rule-based/keyword approach
hai — real semantic decomposition future mein real LLM (Phase 3
provider) ke through hoga; ye abhi structure/seam provide karta hai.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class SubTask:
    id: str
    description: str
    depends_on: List[str] = field(default_factory=list)


class TaskDecomposer:
    """
    Hinglish: Constructor mein ek "recipe book" milta hai — keyword
    se sub-task templates ka mapping. Real system mein ye LLM-driven
    hoga (Planner jaisa), abhi predictable/testable rule-based hai.
    """

    def __init__(self, recipes: dict = None):
        # Hinglish: Default recipe — spec ka "product showcase" example
        self._recipes = recipes or {
            "product showcase": [
                SubTask(id="1", description="Create object"),
                SubTask(id="2", description="Create material", depends_on=["1"]),
                SubTask(id="3", description="Assign material", depends_on=["1", "2"]),
                SubTask(id="4", description="Create camera", depends_on=["1"]),
                SubTask(id="5", description="Render preview", depends_on=["3", "4"]),
            ],
            "sci-fi room": [
                SubTask(id="1", description="Create floor"),
                SubTask(id="2", description="Create walls"),
                SubTask(id="3", description="Create ceiling"),
                SubTask(id="4", description="Add materials", depends_on=["1", "2", "3"]),
                SubTask(id="5", description="Add lights", depends_on=["4"]),
                SubTask(id="6", description="Create camera", depends_on=["5"]),
            ],
        }

    def decompose(self, instruction: str) -> List[SubTask]:
        """
        Hinglish: Instruction mein kaunsi recipe ka keyword match
        karta hai, uski sub-tasks deta hai. Koi match nahi toh ek
        single "atomic" sub-task (pura instruction as-is) return hota
        hai — chhote/simple tasks ke liye decomposition zaroori nahi.
        """
        instruction_lower = instruction.lower()

        for keyword, subtasks in self._recipes.items():
            if keyword in instruction_lower:
                return subtasks

        return [SubTask(id="1", description=instruction)]