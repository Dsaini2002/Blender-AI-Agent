from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.multi_agent.critic_agent import CriticAgent
from blender_ai_agent.reliability.tool_validators import MaterialAssignedValidator, ObjectExistsValidator
from .fakes import FakeBridge, FakeObject


class TestCriticAgent(unittest.TestCase):

    def test_all_checks_pass_gives_full_score(self):
        obj = FakeObject(name="Hero")
        obj.material_name = "Red"
        bridge = FakeBridge(objects=[obj])

        critic = CriticAgent(checks={
            "geometry": ObjectExistsValidator(),
            "material": MaterialAssignedValidator(),
        })

        expected = {"name": "Hero", "object_name": "Hero", "material_name": "Red"}
        report = critic.evaluate(expected, bridge)

        self.assertTrue(report.passed)
        self.assertEqual(report.overall_score, 1.0)

    def test_partial_failure_gives_partial_score_and_feedback(self):
        obj = FakeObject(name="Hero")  # material_name None hai
        bridge = FakeBridge(objects=[obj])

        critic = CriticAgent(checks={
            "geometry": ObjectExistsValidator(),
            "material": MaterialAssignedValidator(),
        })

        expected = {"name": "Hero", "object_name": "Hero", "material_name": "Red"}
        report = critic.evaluate(expected, bridge)

        self.assertFalse(report.passed)
        self.assertEqual(report.overall_score, 0.5)
        self.assertTrue(len(report.feedback) > 0)

    def test_no_checks_gives_zero_score(self):
        bridge = FakeBridge()
        critic = CriticAgent(checks={})

        report = critic.evaluate({}, bridge)

        self.assertEqual(report.overall_score, 0.0)


if __name__ == "__main__":
    unittest.main()