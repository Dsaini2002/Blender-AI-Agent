"""AblationStudy"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List

from ..benchmarks.metrics import BenchmarkMetrics, MetricCalculator
from ..benchmarks.models import BenchmarkTask


@dataclass
class AblationResult:
    variant_a_name: str
    variant_b_name: str
    metrics_a: BenchmarkMetrics
    metrics_b: BenchmarkMetrics

    @property
    def delta(self) -> float:
        return self.metrics_b.success_rate - self.metrics_a.success_rate

    @property
    def better_variant(self) -> str:
        if self.delta > 0:
            return self.variant_b_name
        if self.delta < 0:
            return self.variant_a_name
        return "tie"


class AblationStudy:

    def __init__(self, metric_calculator: MetricCalculator = None):
        self._metric_calculator = metric_calculator or MetricCalculator()

    def compare_variants(
        self,
        variant_a_name: str,
        variant_a_runner: Callable[[List[BenchmarkTask]], list],
        variant_b_name: str,
        variant_b_runner: Callable[[List[BenchmarkTask]], list],
        tasks: List[BenchmarkTask],
    ) -> AblationResult:
        results_a = variant_a_runner(tasks)
        results_b = variant_b_runner(tasks)

        return AblationResult(
            variant_a_name=variant_a_name,
            variant_b_name=variant_b_name,
            metrics_a=self._metric_calculator.calculate(results_a),
            metrics_b=self._metric_calculator.calculate(results_b),
        )