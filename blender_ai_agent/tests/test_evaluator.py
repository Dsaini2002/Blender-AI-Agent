from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.evaluator import Evaluator
from blender_ai_agent.benchmarks.models import BenchmarkTask, TaskStatus
from blender_ai_agent.benchmarks.validation_rules import ObjectExistsRule, ObjectTypeRule
from .fakes import FakeBridge, FakeObject


class TestEvaluator(unittest.TestCase):

    def test_all_rules_pass_gives_full_score(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero", type_="MESH")])
        task = BenchmarkTask(id="t1", instruction="Create a cube named Hero.")
        rules = [ObjectExistsRule("Hero"), ObjectTypeRule("Hero", "MESH")]

        result = Evaluator().evaluate(task, rules, bridge)

        self.assertEqual(result["status"], TaskStatus.PASS)
        self.assertEqual(result["score"], 1.0)

    def test_partial_failure_gives_partial_score(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero", type_="CAMERA")])
        task = BenchmarkTask(id="t1", instruction="test")
        rules = [ObjectExistsRule("Hero"), ObjectTypeRule("Hero", "MESH")]

        result = Evaluator().evaluate(task, rules, bridge)

        self.assertEqual(result["status"], TaskStatus.FAIL)
        self.assertEqual(result["score"], 0.5)

    def test_no_rules_gives_error_status(self):
        bridge = FakeBridge()
        task = BenchmarkTask(id="t1", instruction="test")

        result = Evaluator().evaluate(task, [], bridge)

        self.assertEqual(result["status"], TaskStatus.ERROR)

    def test_weighted_scoring(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero", type_="MESH")])
        rules_with_weights = [
            (ObjectExistsRule("Hero"), 70),
            (ObjectTypeRule("Hero", "CAMERA"), 30),  # ye fail hoga
        ]

        result = Evaluator().evaluate_weighted(rules_with_weights, bridge)

        self.assertAlmostEqual(result["score"], 0.7)
        self.assertEqual(result["status"], TaskStatus.FAIL)


if __name__ == "__main__":
    unittest.main()