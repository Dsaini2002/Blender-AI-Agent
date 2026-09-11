from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.metrics import BenchmarkMetrics
from blender_ai_agent.benchmarks.reporter import BenchmarkReporter


class TestBenchmarkReporter(unittest.TestCase):

    def test_report_contains_success_rate(self):
        metrics = BenchmarkMetrics(total_tasks=100, passed_tasks=89, success_rate=0.89)
        report = BenchmarkReporter().generate_report(metrics)

        self.assertIn("89%", report)
        self.assertIn("Tasks: 100", report)

    def test_report_contains_performance_section(self):
        metrics = BenchmarkMetrics(average_duration=18.2, average_tool_calls=6.4)
        report = BenchmarkReporter().generate_report(metrics)

        self.assertIn("18.20 sec", report)
        self.assertIn("6.4", report)

    def test_report_contains_version(self):
        metrics = BenchmarkMetrics()
        report = BenchmarkReporter().generate_report(metrics, version="2.0")

        self.assertIn("2.0", report)


if __name__ == "__main__":
    unittest.main()