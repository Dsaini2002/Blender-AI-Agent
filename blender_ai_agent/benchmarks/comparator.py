"""
RegressionDetector / BenchmarkComparator — Step 8.36 / 8.37
==================================================================
Hinglish: Do benchmark runs (jaise "before code change" vs "after
code change") compare karke batata hai kahan improve hua, kahan
regress hua.
"""

from dataclasses import dataclass
from typing import Dict, List

from .metrics import BenchmarkMetrics


@dataclass
class ComparisonResult:
    baseline_success_rate: float
    current_success_rate: float
    delta: float

    @property
    def is_regression(self) -> bool:
        return self.delta < 0

    @property
    def is_improvement(self) -> bool:
        return self.delta > 0


class BenchmarkComparator:

    def compare(self, baseline: BenchmarkMetrics, current: BenchmarkMetrics) -> ComparisonResult:
        delta = current.success_rate - baseline.success_rate
        return ComparisonResult(
            baseline_success_rate=baseline.success_rate,
            current_success_rate=current.success_rate,
            delta=delta,
        )

    def detect_regression(self, baseline: BenchmarkMetrics, current: BenchmarkMetrics, threshold: float = 0.0) -> bool:
        """Hinglish: threshold se zyada girawat ho toh regression maano (default: koi bhi girawat)."""
        comparison = self.compare(baseline, current)
        return comparison.delta < -threshold

    def compare_by_category(
        self, baseline_by_category: Dict[str, float], current_by_category: Dict[str, float]
    ) -> Dict[str, float]:
        """Hinglish: Step 8.37 — category-wise comparison (Objects, Materials, etc.)."""
        deltas = {}
        for category in set(baseline_by_category) | set(current_by_category):
            base = baseline_by_category.get(category, 0.0)
            curr = current_by_category.get(category, 0.0)
            deltas[category] = curr - base
        return deltas