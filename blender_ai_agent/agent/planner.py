"""
Planner — Step 3.6
=====================
Hinglish: Planner vs Agent ka farak:

    Agent   -> "Kya karna hai" decide karta hai (LLM se poochta hai)
    Planner -> LLM ke jawab ko EXECUTABLE STEPS ki ordered list mein todta hai
    Executor (ExecutionLoop) -> "Kaise execute karna hai" (Tool ke through)

Abhi ke liye simple hai: LLM response mein jitne tool_calls hain,
unhi ko order mein "Plan" bana dete hain. Isse ek seam mil jaata hai
— future mein agar LLM 5 tool calls ek saath bheje jinme dependency
ho (jaise "material create" pehle, "assign" baad mein), Planner
yahi jagah hai jahan reordering/deduplication add hogi, bina
ExecutionLoop ko chhue.
"""

from dataclasses import dataclass, field
from typing import List

from .models import ModelResponse, ToolCall


@dataclass
class PlanStep:
    """Ek single execution step — abhi sirf ek tool call hai."""
    tool_call: ToolCall


@dataclass
class Plan:
    """Ordered steps ki list — Executor isi order mein chalayega."""
    steps: List[PlanStep] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return len(self.steps) == 0


class Planner:
    """
    Hinglish: Abhi LLM khud order decide karta hai (jis order mein
    tool_calls diye), Planner sirf unhe Plan object mein wrap karta
    hai — taaki Executor ko pata rahe "steps" ek defined shape mein
    hain, raw response ka structure jaanne ki zaroorat nahi.
    """

    def create_plan(self, response: ModelResponse) -> Plan:
        steps = [PlanStep(tool_call=tc) for tc in response.tool_calls]
        return Plan(steps=steps)