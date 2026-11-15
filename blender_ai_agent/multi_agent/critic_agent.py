"""CriticAgent"""

from dataclasses import dataclass, field
from typing import Dict, List

from ..reliability.validator import ValidationResult, Validator


@dataclass
class CriticReport:
    checks: List[ValidationResult] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        if not self.checks:
            return 0.0
        return sum(1 for c in self.checks if c.valid) / len(self.checks)

    @property
    def passed(self) -> bool:
        return self.overall_score == 1.0

    @property
    def feedback(self) -> List[str]:
        feedback_list = []
        for check in self.checks:
            if not check.valid:
                feedback_list.extend(check.reasons)
        return feedback_list


class CriticAgent:

    def __init__(self, checks: Dict[str, Validator]):
        self._checks = checks

    def evaluate(self, expected: dict, bridge) -> CriticReport:
        report = CriticReport()
        for aspect_name, validator in self._checks.items():
            result = validator.validate(expected, bridge)
            report.checks.append(result)
        return report