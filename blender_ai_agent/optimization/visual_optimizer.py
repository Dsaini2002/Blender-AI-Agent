"""VisualQualityOptimizer"""

from dataclasses import dataclass, field
from typing import Callable, List


@dataclass
class OptimizationAttempt:
    iteration: int
    score: float


@dataclass
class OptimizationResult:
    attempts: List[OptimizationAttempt] = field(default_factory=list)
    final_score: float = 0.0
    stopped_reason: str = ""

    @property
    def improved(self) -> bool:
        if len(self.attempts) < 2:
            return False
        return self.attempts[-1].score > self.attempts[0].score


class VisualQualityOptimizer:

    def __init__(self, render_fn: Callable, score_fn: Callable, improve_fn: Callable, max_iterations: int = 3, target_score: float = 0.9):
        self._render_fn = render_fn
        self._score_fn = score_fn
        self._improve_fn = improve_fn
        self._max_iterations = max_iterations
        self._target_score = target_score

    def optimize(self) -> OptimizationResult:
        result = OptimizationResult()

        for iteration in range(1, self._max_iterations + 1):
            observation = self._render_fn()
            score = self._score_fn(observation)
            result.attempts.append(OptimizationAttempt(iteration=iteration, score=score))

            if score >= self._target_score:
                result.stopped_reason = "target_reached"
                result.final_score = score
                return result

            if iteration < self._max_iterations:
                self._improve_fn(observation)

        result.stopped_reason = "max_iterations_reached"
        result.final_score = result.attempts[-1].score
        return result