"""
MetricCalculator — Step 8.25 / 8.26
========================================
Hinglish: Multiple BenchmarkResults se aggregate statistics banata hai.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .models import BenchmarkResult, TaskStatus


@dataclass
class BenchmarkMetrics:
    total_tasks: int = 0
    passed_tasks: int = 0
    success_rate: float = 0.0
    average_score: float = 0.0
    average_duration: float = 0.0
    average_tool_calls: float = 0.0
    average_retries: float = 0.0
    total_rollbacks: int = 0
    status_breakdown: Dict[str, int] = field(default_factory=dict)


class MetricCalculator:

    def calculate(self, results: List[BenchmarkResult]) -> BenchmarkMetrics:
        if not results:
            return BenchmarkMetrics()

        total = len(results)
        passed = sum(1 for r in results if r.status == TaskStatus.PASS)

        status_breakdown: Dict[str, int] = {}
        for r in results:
            status_breakdown[r.status.value] = status_breakdown.get(r.status.value, 0) + 1

        return BenchmarkMetrics(
            total_tasks=total,
            passed_tasks=passed,
            success_rate=passed / total,
            average_score=sum(r.score for r in results) / total,
            average_duration=sum(r.duration for r in results) / total,
            average_tool_calls=sum(r.tool_calls for r in results) / total,
            average_retries=sum(r.retries for r in results) / total,
            total_rollbacks=sum(r.rollbacks for r in results),
            status_breakdown=status_breakdown,
        )