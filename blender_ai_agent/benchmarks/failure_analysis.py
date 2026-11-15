"""Failure Classification + Analysis"""

from dataclasses import dataclass
from enum import Enum
from typing import List

from .models import BenchmarkResult, TaskStatus


class FailureCategory(str, Enum):
    PLANNING_FAILURE = "PLANNING_FAILURE"
    TOOL_FAILURE = "TOOL_FAILURE"
    BLENDER_FAILURE = "BLENDER_FAILURE"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    VISION_FAILURE = "VISION_FAILURE"
    RECOVERY_FAILURE = "RECOVERY_FAILURE"
    PERMISSION_FAILURE = "PERMISSION_FAILURE"
    TIMEOUT = "TIMEOUT"
    UNKNOWN_FAILURE = "UNKNOWN_FAILURE"


@dataclass
class FailureDiagnosis:
    task_id: str
    category: FailureCategory
    summary: str


class FailureAnalyzer:

    def classify(self, result: BenchmarkResult) -> FailureCategory:
        if result.status == TaskStatus.TIMEOUT:
            return FailureCategory.TIMEOUT

        if result.status == TaskStatus.ERROR:
            error_text = " ".join(result.errors).lower()
            if "vision" in error_text:
                return FailureCategory.VISION_FAILURE
            if "permission" in error_text:
                return FailureCategory.PERMISSION_FAILURE
            if "tool" in error_text:
                return FailureCategory.TOOL_FAILURE
            return FailureCategory.UNKNOWN_FAILURE

        if result.status == TaskStatus.FAIL:
            if result.rollbacks > 0:
                return FailureCategory.RECOVERY_FAILURE
            if result.failed_rules:
                return FailureCategory.VALIDATION_FAILURE
            return FailureCategory.UNKNOWN_FAILURE

        return FailureCategory.UNKNOWN_FAILURE

    def analyze(self, result: BenchmarkResult) -> FailureDiagnosis:
        category = self.classify(result)

        if category == FailureCategory.VALIDATION_FAILURE and result.failed_rules:
            failed = result.validation_results
            mismatches = [r for r in failed if not r.passed]
            details = "; ".join(
                f"{r.rule_id}: expected {r.expected}, got {r.actual}" for r in mismatches
            )
            summary = f"Validation mismatch — {details}"
        elif result.errors:
            summary = "; ".join(result.errors)
        else:
            summary = f"Task ended with status {result.status.value}."

        return FailureDiagnosis(task_id=result.task_id, category=category, summary=summary)

    def analyze_all(self, results: List[BenchmarkResult]) -> List[FailureDiagnosis]:
        return [self.analyze(r) for r in results if r.status != TaskStatus.PASS]