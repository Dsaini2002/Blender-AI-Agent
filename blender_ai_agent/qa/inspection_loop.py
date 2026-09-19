"""
InspectionLoop — Step 12.6
==============================
Hinglish: Yehi diagram wala "inspect -> fix -> re-inspect -> pass/fail"
loop hai, `RepairableExecutionLoop` (Phase 4) jaisa hi pattern —
lekin tool-execution repair karne ki jagah, scene-QUALITY repair
karta hai.

Flow:
    inspect() -> issues mile?
        nahi -> PASS, turant return
        haan -> auto-fixable issues fix karo -> re-inspect
                -> retry limit tak repeat, warna FAIL

`GuardrailMonitor` (Phase 11) hi retry-limit enforce karta hai — koi
naya retry-counting mechanism nahi banaya, existing infra reuse hui.
"""

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
                # Ya toh koi fixable issue nahi bacha, ya retry-budget khatam —
                # dono cases mein FAIL report ke saath ruk jaate hain (koi
                # infinite loop nahi, jaisa GuardrailMonitor ka poora purpose hai).
                break

            self._fixer.fix(fixable)
            self._guardrail.record_retry()
            issues = self._inspector.inspect()

        return InspectionReport(issues=issues, retries_used=self._guardrail.retries_taken)
