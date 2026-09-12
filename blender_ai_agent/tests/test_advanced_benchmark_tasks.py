from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.tasks.advanced_tasks import (
    create_bounce_animation_rules,
    create_bounce_animation_task,
    create_geometry_nodes_rules,
    create_geometry_nodes_task,
)
from .fakes import FakeBridge, FakeObject


class TestGeometryNodesTask(unittest.TestCase):

    def test_task_definition(self):
        task = create_geometry_nodes_task()
        self.assertEqual(task.category, "geometry_nodes")

    def test_rule_passes_when_node_group_exists(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        bridge.add_geometry_nodes("Hero", "Scatter")

        rules = create_geometry_nodes_rules(bridge)
        results = [r.validate(bridge) for r in rules]

        self.assertTrue(all(r.passed for r in results))

    def test_rule_fails_when_missing(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        rules = create_geometry_nodes_rules(bridge)

        results = [r.validate(bridge) for r in rules]

        self.assertFalse(all(r.passed for r in results))


class TestBounceAnimationTask(unittest.TestCase):

    def test_task_definition(self):
        task = create_bounce_animation_task()
        self.assertEqual(task.category, "animation")

    def test_rules_pass_when_keyframes_exist(self):
        bridge = FakeBridge(objects=[FakeObject(name="Ball")])
        bridge.insert_keyframe("Ball", frame=1)
        bridge.insert_keyframe("Ball", frame=20)

        rules = create_bounce_animation_rules(bridge)
        results = [r.validate(bridge) for r in rules]

        self.assertTrue(all(r.passed for r in results))

    def test_rules_fail_when_keyframes_missing(self):
        bridge = FakeBridge(objects=[FakeObject(name="Ball")])
        rules = create_bounce_animation_rules(bridge)

        results = [r.validate(bridge) for r in rules]

        self.assertFalse(all(r.passed for r in results))


if __name__ == "__main__":
    unittest.main()