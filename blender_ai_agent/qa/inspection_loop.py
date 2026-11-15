"""InspectionLoop"""

from ..autonomy.guardrails import GuardrailLimits, GuardrailMonitor
from .fixer import GeometryFixer
from .geometry_inspector import GeometryInspector
from .models import InspectionReport


class InspectionLoop:
    def __init__(self, bridge, inspector: GeometryInspector = None, fixer: GeometryFixer = None, max_retries: int = 3):
        self._bridge = bridge
        self._inspector = inspector or GeometryInspector(bridge)
        self._fixer = fixer or GeometryFixer(bridge)
        self._guardrail = GuardrailMonitor(GuardrailLimits(max_retries=max_retries))

    def run(self) -> InspectionReport:
        issues = self._inspector.inspect()

        while issues:
            fixable = [issue for issue in issues if issue.auto_fixable]

            if not fixable or not self._guardrail.is_within_limits:
                break

            self._fixer.fix(fixable)
            self._guardrail.record_retry()
            issues = self._inspector.inspect()

        return InspectionReport(issues=issues, retries_used=self._guardrail.retries_taken)
