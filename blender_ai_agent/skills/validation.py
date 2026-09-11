"""
Skill Validation — Step 7.15
================================
Hinglish: Skill "success" bola matlab actually scene mein sab theek
hua, ye guarantee nahi. Phase 4 ke Validators yahan reuse karte hain
— exactly jaisa RepairableExecutionLoop tool-level validation karta
hai, waisa hi skill-level bhi.
"""

from typing import Dict, List

from ..reliability.validator import ValidationResult, Validator
from .base import SkillResult


class SkillValidator:
    """
    Hinglish: Skill ke completed steps ke against, har step ka apna
    Validator (agar registered hai) chalata hai — scene ko source of
    truth maan kar.
    """

    def __init__(self, bridge, step_validators: Dict[str, Validator] = None):
        self._bridge = bridge
        self._step_validators = step_validators or {}

    def validate(self, skill_result: SkillResult, expected_by_step: Dict[str, dict]) -> ValidationResult:
        """
        Hinglish: `expected_by_step` — har completed step ke liye
        expected outcome dict (jaisa Phase 4 validators expect karte
        hain). Agar koi step ka validator registered nahi hai, us
        step ko skip kar dete hain (assume trust the tool result).
        """
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