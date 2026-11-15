"""Skill Validation"""

from typing import Dict, List

from ..reliability.validator import ValidationResult, Validator
from .base import SkillResult


class SkillValidator:

    def __init__(self, bridge, step_validators: Dict[str, Validator] = None):
        self._bridge = bridge
        self._step_validators = step_validators or {}

    def validate(self, skill_result: SkillResult, expected_by_step: Dict[str, dict]) -> ValidationResult:
        if not skill_result.success:
            return ValidationResult.failed(skill_result.error or "Skill did not complete successfully.")

        all_reasons: List[str] = []

        for step_name in skill_result.steps_completed:
            validator = self._step_validators.get(step_name)
            if validator is None:
                continue

            expected = expected_by_step.get(step_name, {})
            result = validator.validate(expected, self._bridge)
            if not result.valid:
                all_reasons.extend(result.reasons)

        if all_reasons:
            return ValidationResult.failed(*all_reasons)

        return ValidationResult.ok()