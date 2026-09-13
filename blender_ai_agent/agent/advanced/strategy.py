"""
StrategySelector — Step 11.6
=================================
Hinglish: Ek hi goal ko multiple tareekon se achieve kiya ja sakta
hai (spec ka example: rounded object -> mesh modeling vs bevel
modifier vs geometry nodes). Ye class un strategies ko score karke
best choose karti hai.

Score = reliability + quality - cost (Step 11.6 ka formula, simplified)
"""

from dataclasses import dataclass
from typing import Callable, List


@dataclass
class Strategy:
    name: str
    reliability: float   # 0.0-1.0 — kitni baar successfully kaam karta hai (historical/estimated)
    expected_quality: float  # 0.0-1.0
    execution_cost: float    # 0.0-1.0 (zyada = zyada mehnga/dheema)
    action: Callable = None  # actual execution callable — agent isse call karega

    def __post_init__(self):
        for field_name, value in (
            ("reliability", self.reliability),
            ("expected_quality", self.expected_quality),
            ("execution_cost", self.execution_cost),
        ):
            if not (0.0 <= value <= 1.0):
                raise ValueError(f"Strategy.{field_name} must be between 0.0 and 1.0")

    @property
    def score(self) -> float:
        """Hinglish: Higher reliability/quality achha, higher cost bura."""
        return self.reliability + self.expected_quality - self.execution_cost


class StrategySelector:

    def select_best(self, strategies: List[Strategy]) -> Strategy:
        if not strategies:
            raise ValueError("No strategies provided to select from.")
        return max(strategies, key=lambda s: s.score)

    def rank(self, strategies: List[Strategy]) -> List[Strategy]:
        """Hinglish: Sabse best se sabse worst tak sorted list — fallback options ke liye useful."""
        return sorted(strategies, key=lambda s: s.score, reverse=True)