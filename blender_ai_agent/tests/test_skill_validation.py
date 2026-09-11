from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability.tool_validators import ObjectExistsValidator
from blender_ai_agent.skills.base import SkillResult
from blender_ai_agent.skills.validation import SkillValidator
from .fakes import FakeBridge, FakeObject


class TestSkillValidator(unittest.TestCase):

    def test_failed_skill_result_fails_validation_immediately(self):
        bridge = FakeBridge()
        validator = SkillValidator(bridge)

        result = validator.validate(SkillResult.fail("boom"), expected_by_step={})

        self.assertFalse(result.valid)

    def test_successful_skill_with_no_registered_validators_passes(self):
        bridge = FakeBridge()
        validator = SkillValidator(bridge)

        skill_result = SkillResult.ok(steps_completed=["object.create"])
        result = validator.validate(skill_result, expected_by_step={})

        self.assertTrue(result.valid)

    def test_step_validator_catches_scene_mismatch(self):
        bridge = FakeBridge(objects=[])  # object.create "succeeded" but object missing
        validator = SkillValidator(bridge, step_validators={"object.create": ObjectExistsValidator()})

        skill_result = SkillResult.ok(steps_completed=["object.create"])
        result = validator.validate(
            skill_result,
            expected_by_step={"object.create": {"name": "Vase"}},
        )

        self.assertFalse(result.valid)

    def test_step_validator_passes_when_scene_matches(self):
        bridge = FakeBridge(objects=[FakeObject(name="Vase")])
        validator = SkillValidator(bridge, step_validators={"object.create": ObjectExistsValidator()})

        skill_result = SkillResult.ok(steps_completed=["object.create"])
        result = validator.validate(
            skill_result,
            expected_by_step={"object.create": {"name": "Vase"}},
        )

        self.assertTrue(result.valid)


if __name__ == "__main__":
    unittest.main()