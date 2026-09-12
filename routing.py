"""
ModelRouter — Step 11.14 / 11.15
=====================================
Hinglish: Har task ke liye SAME provider use karna wasteful hai —
simple task ke liye "strong" (expensive) model chalana cost-inefficient
hai. Router task ki complexity dekh kar decide karta hai kaunsa
provider-tier use karna hai.

Abhi ke liye rule-based hai (spec khud kehta hai actual routing logic
baad mein refine hogi) — structure/seam yahan zaroori hai.
"""

from enum import Enum
from typing import Optional


class ModelTier(str, Enum):
    FAST = "fast"        # simple, deterministic-ish tasks
    STRONG = "strong"     # complex planning/reasoning
    VISION = "vision"     # visual ambiguity involved


class ModelRouter:

    def __init__(self, providers: dict):
        """
        Hinglish: `providers` = {"fast": provider1, "strong": provider2,
        "vision": provider3} — Dependency Injection, router khud
        provider nahi banata.
        """
        self._providers = providers

    def route(self, instruction: str, requires_vision: bool = False, subtask_count: int = 1) -> ModelTier:
        """
        Hinglish: Routing factors (Step 11.15):
          - requires_vision -> VISION tier
          - subtask_count > 1 (multi-step/complex) -> STRONG tier
          - warna -> FAST tier
        """
        if requires_vision:
            return ModelTier.VISION
        if subtask_count > 1:
            return ModelTier.STRONG
        return ModelTier.FAST

    def get_provider(self, tier: ModelTier):
        if tier.value not in self._providers:
            raise KeyError(f"No provider registered for tier '{tier.value}'.")
        return self._providers[tier.value]

    def route_and_get(self, instruction: str, requires_vision: bool = False, subtask_count: int = 1):
        tier = self.route(instruction, requires_vision, subtask_count)
        return self.get_provider(tier)