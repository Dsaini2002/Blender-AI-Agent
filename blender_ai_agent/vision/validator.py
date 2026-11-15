"""VisualValidator"""

from ..reliability.validator import ValidationResult
from .models import VisualObservation


class VisualValidator:

    def validate(self, observation: VisualObservation, expected: dict) -> ValidationResult:
        reasons = []

        min_confidence = expected.get("min_confidence")
        if min_confidence is not None and observation.confidence < min_confidence:
            reasons.append(
                f"Confidence {observation.confidence} is below required {min_confidence}."
            )

        required_objects = expected.get("required_objects")
        if required_objects:
            missing = [obj for obj in required_objects if obj not in observation.objects_detected]
            if missing:
                reasons.append(f"Expected objects not detected: {missing}")

        if expected.get("no_issues") and observation.issues:
            reasons.append(f"Unexpected visual issues found: {observation.issues}")

        if reasons:
            return ValidationResult.failed(*reasons)

        return ValidationResult.ok()