from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.comparator import BenchmarkComparator
from blender_ai_agent.benchmarks.metrics import BenchmarkMetrics


class TestBenchmarkComparator(unittest.TestCase):

    def test_improvement_detected(self):
        baseline = BenchmarkMetrics(success_rate=0.83)
        current = BenchmarkMetrics(success_rate=0.90)

        comparison = BenchmarkComparator().compare(baseline, current)

        self.assertTrue(comparison.is_improvement)
        self.assertAlmostEqual(comparison.delta, 0.07)

    def test_regression_detected(self):
        baseline = BenchmarkMetrics(success_rate=0.90)
        current = BenchmarkMetrics(success_rate=0.83)

        comparison = BenchmarkComparator().compare(baseline, current)

        self.assertTrue(comparison.is_regression)

    def test_detect_regression_boolean(self):
        baseline = BenchmarkMetrics(success_rate=0.90)
        current = BenchmarkMetrics(success_rate=0.83)

        is_regression = BenchmarkComparator().detect_regression(baseline, current)

        self.assertTrue(is_regression)

    def test_no_regression_when_equal(self):
        baseline = BenchmarkMetrics(success_rate=0.90)
        current = BenchmarkMetrics(success_rate=0.90)

        is_regression = BenchmarkComparator().detect_regression(baseline, current)

        self.assertFalse(is_regression)

    def test_compare_by_category(self):
        baseline = {"objects": 0.94, "materials": 0.89}
        current = {"objects": 0.91, "materials": 0.93}

        deltas = BenchmarkComparator().compare_by_category(baseline, current)

        self.assertAlmostEqual(deltas["objects"], -0.03)
        self.assertAlmostEqual(deltas["materials"], 0.04)


if __name__ == "__main__":
    unittest.main()