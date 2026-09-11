from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.tasks.basic_tasks import create_cube_rules, create_cube_task
from .fakes import FakeBridge, FakeObject


class TestCreateCubeTask(unittest.TestCase):

    def test_task_definition(self):
        task = create_cube_task()
        self.assertEqual(task.id, "object_create_001")
        self.assertIn("Hero", task.instruction)

    def test_rules_pass_when_hero_exists(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero", type_="MESH")])
        rules = create_cube_rules(bridge)

        results = [rule.validate(bridge) for rule in rules]

        self.assertTrue(all(r.passed for r in results))

    def test_rules_fail_when_hero_missing(self):
        bridge = FakeBridge(objects=[])
        rules = create_cube_rules(bridge)

        results = [rule.validate(bridge) for rule in rules]

        self.assertFalse(all(r.passed for r in results))


if __name__ == "__main__":
    unittest.main()