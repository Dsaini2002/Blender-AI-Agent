from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.metrics import MetricCalculator
from blender_ai_agent.benchmarks.models import BenchmarkResult, TaskStatus


class TestMetricCalculator(unittest.TestCase):

    def test_empty_results_gives_zero_metrics(self):
        metrics = MetricCalculator().calculate([])
        self.assertEqual(metrics.total_tasks, 0)
        self.assertEqual(metrics.success_rate, 0.0)

    def test_success_rate_calculation(self):
        results = [
            BenchmarkResult(task_id="t1", status=TaskStatus.PASS, score=1.0),
            BenchmarkResult(task_id="t2", status=TaskStatus.PASS, score=1.0),
            BenchmarkResult(task_id="t3", status=TaskStatus.FAIL, score=0.5),
            BenchmarkResult(task_id="t4", status=TaskStatus.PASS, score=1.0),
        ]

        metrics = MetricCalculator().calculate(results)

        self.assertEqual(metrics.total_tasks, 4)
        self.assertEqual(metrics.passed_tasks, 3)
        self.assertEqual(metrics.success_rate, 0.75)

    def test_average_score(self):
        results = [
            BenchmarkResult(task_id="t1", status=TaskStatus.PASS, score=1.0),
            BenchmarkResult(task_id="t2", status=TaskStatus.FAIL, score=0.5),
        ]

        metrics = MetricCalculator().calculate(results)

        self.assertEqual(metrics.average_score, 0.75)

    def test_status_breakdown(self):
        results = [
            BenchmarkResult(task_id="t1", status=TaskStatus.PASS, score=1.0),
            BenchmarkResult(task_id="t2", status=TaskStatus.TIMEOUT, score=0.0),
        ]

        metrics = MetricCalculator().calculate(results)

        self.assertEqual(metrics.status_breakdown["PASS"], 1)
        self.assertEqual(metrics.status_breakdown["TIMEOUT"], 1)

    def test_total_rollbacks_summed(self):
        results = [
            BenchmarkResult(task_id="t1", status=TaskStatus.PASS, score=1.0, rollbacks=0),
            BenchmarkResult(task_id="t2", status=TaskStatus.FAIL, score=0.0, rollbacks=2),
        ]

        metrics = MetricCalculator().calculate(results)

        self.assertEqual(metrics.total_rollbacks, 2)


if __name__ == "__main__":
    unittest.main()