"""StrategySelector
================

Score = reliability + quality - cost
"""

from dataclasses import dataclass
from typing import Callable, List


@dataclass
class Strategy:
    name: str
    reliability: float
    expected_quality: float  # 0.0-1.0
    execution_cost: float
    action: Callable = None

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
        return self.reliability + self.expected_quality - self.execution_cost


class StrategySelector:

    def select_best(self, strategies: List[Strategy]) -> Strategy:
        if not strategies:
            raise ValueError("No strategies provided to select from.")
        return max(strategies, key=lambda s: s.score)

    def rank(self, strategies: List[Strategy]) -> List[Strategy]:
        return sorted(strategies, key=lambda s: s.score, reverse=True)