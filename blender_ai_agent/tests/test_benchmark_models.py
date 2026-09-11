from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.models import (
    BenchmarkResult,
    BenchmarkTask,
    Difficulty,
    TaskStatus,
    ValidationResult,
)


class TestBenchmarkTask(unittest.TestCase):

    def test_valid_task(self):
        task = BenchmarkTask(id="object_create_001", instruction="Create a cube named Hero.")
        self.assertEqual(task.difficulty, Difficulty.EASY)
        self.assertEqual(task.timeout, 120)

    def test_empty_id_raises(self):
        with self.assertRaises(ValueError):
            BenchmarkTask(id="", instruction="test")

    def test_empty_instruction_raises(self):
        with self.assertRaises(ValueError):
            BenchmarkTask(id="t1", instruction="")


class TestValidationResult(unittest.TestCase):

    def test_passed_result_has_score_one(self):
        result = ValidationResult(rule_id="r1", passed=True)
        self.assertEqual(result.score, 1.0)

    def test_failed_result_has_score_zero(self):
        result = ValidationResult(rule_id="r1", passed=False)
        self.assertEqual(result.score, 0.0)


class TestBenchmarkResult(unittest.TestCase):

    def test_success_true_when_status_pass(self):
        result = BenchmarkResult(task_id="t1", status=TaskStatus.PASS, score=1.0)
        self.assertTrue(result.success)

    def test_success_false_when_status_fail(self):
        result = BenchmarkResult(task_id="t1", status=TaskStatus.FAIL, score=0.5)
        self.assertFalse(result.success)

    def test_passed_and_failed_rules_split_correctly(self):
        result = BenchmarkResult(
            task_id="t1",
            status=TaskStatus.FAIL,
            score=0.5,
            validation_results=[
                ValidationResult(rule_id="a", passed=True),
                ValidationResult(rule_id="b", passed=False),
            ],
        )
        self.assertEqual(result.passed_rules, ["a"])
        self.assertEqual(result.failed_rules, ["b"])


if __name__ == "__main__":
    unittest.main()