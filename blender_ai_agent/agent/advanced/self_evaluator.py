"""SelfEvaluator"""

from dataclasses import dataclass, field
from typing import List, Optional

from ...reliability.validator import ValidationResult


@dataclass
class SelfEvaluationReport:
    structural_result: Optional[ValidationResult] = None
    visual_result: Optional[ValidationResult] = None

    @property
    def overall_valid(self) -> bool:
        results = [r for r in (self.structural_result, self.visual_result) if r is not None]
        if not results:
            return False
        return all(r.valid for r in results)

    @property
    def all_reasons(self) -> List[str]:
        reasons = []
        if self.structural_result and not self.structural_result.valid:
            reasons.extend(self.structural_result.reasons)
        if self.visual_result and not self.visual_result.valid:
            reasons.extend(self.visual_result.reasons)
        return reasons


class SelfEvaluator:

    def __init__(self, structural_validators=None, visual_validator=None):
        self._structural_validators = structural_validators or {}
        self._visual_validator = visual_validator

    def evaluate(self, tool_name: str, expected: dict, bridge, visual_observation=None, visual_expected=None) -> SelfEvaluationReport:
        report = SelfEvaluationReport()

        validator = self._structural_validators.get(tool_name)
        if validator is not None:
            report.structural_result = validator.validate(expected, bridge)

        if self._visual_validator is not None and visual_observation is not None:
            report.visual_result = self._visual_validator.validate(visual_observation, visual_expected or {})

        return report