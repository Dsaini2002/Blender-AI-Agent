from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.stress_test import StressTest
from .fakes import FakeBridge, FakeObject


class TestStressTest(unittest.TestCase):

    def test_runs_for_each_object_count(self):
        stress = StressTest()

        def scene_builder(count):
            return FakeBridge(objects=[FakeObject(name=f"Obj{i}") for i in range(count)])

        def task_runner(bridge):
            return len(bridge.get_objects())  # tool_calls proxy

        results = stress.run([10, 100], scene_builder, task_runner)

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].object_count, 10)
        self.assertEqual(results[1].tool_calls, 100)

    def test_scales_reasonably_true_for_fast_execution(self):
        stress = StressTest()

        def scene_builder(count):
            return FakeBridge()

        def task_runner(bridge):
            return 1

        results = stress.run([10, 100], scene_builder, task_runner)

        self.assertTrue(stress.scales_reasonably(results, max_duration_per_object=1.0))

    def test_scales_reasonably_false_when_too_slow(self):
        stress = StressTest()
        from blender_ai_agent.benchmarks.stress_test import StressTestResult

        results = [StressTestResult(object_count=10, duration_seconds=100.0, tool_calls=5)]

        self.assertFalse(stress.scales_reasonably(results, max_duration_per_object=0.1))


if __name__ == "__main__":
    unittest.main()