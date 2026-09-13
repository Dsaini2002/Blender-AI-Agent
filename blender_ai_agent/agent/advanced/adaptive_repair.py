"""
AdaptiveRepairPlanner — Step 11.8
======================================
Hinglish: Phase 4 ka repair sirf EK strategy try karta tha. Ye class
MULTIPLE candidate repairs generate karti hai aur unhe rank karke
best choose karti hai — spec ke example jaisa.
"""

from dataclasses import dataclass
from typing import Callable, List


@dataclass
class RepairCandidate:
    name: str
    confidence: float
    action: Callable

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("RepairCandidate.confidence must be between 0.0 and 1.0")


class AdaptiveRepairPlanner:

    def __init__(self, candidate_generators: List[Callable] = None):
        self._candidate_generators = candidate_generators or []

    def generate_candidates(self, error) -> List[RepairCandidate]:
        candidates = []
        for generator in self._candidate_generators:
            candidates.extend(generator(error))
        return candidates

    def select_repair(self, error) -> RepairCandidate:
        candidates = self.generate_candidates(error)
        if not candidates:
            raise ValueError("No repair candidates generated for this error.")
        return max(candidates, key=lambda c: c.confidence)

    def rank_candidates(self, error) -> List[RepairCandidate]:
        return sorted(self.generate_candidates(error), key=lambda c: c.confidence, reverse=True)