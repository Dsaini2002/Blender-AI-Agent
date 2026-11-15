from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.qa.inspection_loop import InspectionLoop
from .fakes import FakeBridge, FakeObject


class NoOpFixer:

    def fix(self, issues):
        return []


class TestInspectionLoop(unittest.TestCase):

    def test_clean_scene_passes_immediately(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        loop = InspectionLoop(bridge)

        report = loop.run()

        self.assertTrue(report.passed)
        self.assertEqual(report.retries_used, 0)

    def test_fixable_issue_gets_resolved_and_passes(self):
        obj = FakeObject(name="Cube", flipped_normal_count=4)
        bridge = FakeBridge(objects=[obj])
        loop = InspectionLoop(bridge)

        report = loop.run()

        self.assertTrue(report.passed)
        self.assertEqual(report.retries_used, 1)

    def test_unfixable_issue_stops_immediately_without_retry(self):
        obj = FakeObject(name="Cube", non_manifold_edge_count=2)
        bridge = FakeBridge(objects=[obj])
        loop = InspectionLoop(bridge)

        report = loop.run()

        self.assertFalse(report.passed)
        self.assertEqual(report.retries_used, 0)
        self.assertEqual(len(report.blocking_issues), 1)

    def test_guardrail_stops_infinite_retry_loop(self):
        obj = FakeObject(name="Cube", flipped_normal_count=4)
        bridge = FakeBridge(objects=[obj])
        loop = InspectionLoop(bridge, fixer=NoOpFixer(), max_retries=2)

        report = loop.run()

        self.assertFalse(report.passed)
        self.assertEqual(report.retries_used, 3)


if __name__ == "__main__":
    unittest.main()
