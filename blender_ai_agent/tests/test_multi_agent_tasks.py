from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.tasks.multi_agent_tasks import (
    create_product_scene_rules,
    create_product_scene_task,
)
from .fakes import FakeBridge, FakeObject


class TestMultiAgentBenchmarkTask(unittest.TestCase):

    def test_task_definition(self):
        task = create_product_scene_task()
        self.assertEqual(task.category, "multi_agent")

    def test_rules_pass_when_scene_correct(self):
        obj = FakeObject(name="Hero")
        obj.material_name = "Red"
        bridge = FakeBridge(objects=[obj])

        rules = create_product_scene_rules(bridge)
        results = [r.validate(bridge) for r in rules]

        self.assertTrue(all(r.passed for r in results))

    def test_rules_fail_when_scene_incomplete(self):
        bridge = FakeBridge(objects=[])
        rules = create_product_scene_rules(bridge)

        results = [r.validate(bridge) for r in rules]

        self.assertFalse(all(r.passed for r in results))


if __name__ == "__main__":
    unittest.main()