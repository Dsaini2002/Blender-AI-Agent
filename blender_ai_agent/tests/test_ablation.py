from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.models import BenchmarkResult, BenchmarkTask, TaskStatus
from blender_ai_agent.research.ablation import AblationStudy


class TestAblationStudy(unittest.TestCase):

    def test_compare_variants_computes_delta(self):
        study = AblationStudy()
        tasks = [BenchmarkTask(id="t1", instruction="test")]

        def runner_without_vision(tasks):
            return [BenchmarkResult(task_id="t1", status=TaskStatus.FAIL, score=0.5)]

        def runner_with_vision(tasks):
            return [BenchmarkResult(task_id="t1", status=TaskStatus.PASS, score=1.0)]

        result = study.compare_variants(
            "without_vision", runner_without_vision,
            "with_vision", runner_with_vision,
            tasks,
        )

        self.assertEqual(result.better_variant, "with_vision")
        self.assertGreater(result.delta, 0)

    def test_tie_when_equal_performance(self):
        study = AblationStudy()
        tasks = [BenchmarkTask(id="t1", instruction="test")]

        def runner(tasks):
            return [BenchmarkResult(task_id="t1", status=TaskStatus.PASS, score=1.0)]

        result = study.compare_variants("a", runner, "b", runner, tasks)

        self.assertEqual(result.better_variant, "tie")
        self.assertEqual(result.delta, 0.0)


if __name__ == "__main__":
    unittest.main()