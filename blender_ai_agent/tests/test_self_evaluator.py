from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.self_evaluator import SelfEvaluator
from blender_ai_agent.reliability.tool_validators import ObjectExistsValidator
from blender_ai_agent.vision.models import VisualObservation
from blender_ai_agent.vision.validator import VisualValidator
from .fakes import FakeBridge, FakeObject


class TestSelfEvaluator(unittest.TestCase):

    def test_structural_only_pass(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        evaluator = SelfEvaluator(structural_validators={"object.create": ObjectExistsValidator()})

        report = evaluator.evaluate("object.create", {"name": "Hero"}, bridge)

        self.assertTrue(report.overall_valid)

    def test_structural_only_fail(self):
        bridge = FakeBridge(objects=[])
        evaluator = SelfEvaluator(structural_validators={"object.create": ObjectExistsValidator()})

        report = evaluator.evaluate("object.create", {"name": "Hero"}, bridge)

        self.assertFalse(report.overall_valid)
        self.assertTrue(len(report.all_reasons) > 0)

    def test_no_validators_means_not_valid(self):
        """Hinglish: Koi validator registered nahi -> hum kuch verify nahi kar sake, safe default: invalid."""
        bridge = FakeBridge()
        evaluator = SelfEvaluator()

        report = evaluator.evaluate("unknown.tool", {}, bridge)

        self.assertFalse(report.overall_valid)

    def test_combined_structural_and_visual(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        evaluator = SelfEvaluator(
            structural_validators={"object.create": ObjectExistsValidator()},
            visual_validator=VisualValidator(),
        )

        observation = VisualObservation(description="hero visible", objects_detected=["hero"], confidence=0.9)

        report = evaluator.evaluate(
            "object.create", {"name": "Hero"}, bridge,
            visual_observation=observation,
            visual_expected={"min_confidence": 0.5},
        )

        self.assertTrue(report.overall_valid)

    def test_visual_failure_makes_overall_invalid_even_if_structural_passes(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        evaluator = SelfEvaluator(
            structural_validators={"object.create": ObjectExistsValidator()},
            visual_validator=VisualValidator(),
        )

        observation = VisualObservation(description="unclear", confidence=0.1)

        report = evaluator.evaluate(
            "object.create", {"name": "Hero"}, bridge,
            visual_observation=observation,
            visual_expected={"min_confidence": 0.9},
        )

        self.assertFalse(report.overall_valid)


if __name__ == "__main__":
    unittest.main()