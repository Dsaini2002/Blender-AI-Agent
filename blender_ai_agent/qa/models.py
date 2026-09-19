"""
QA Models — Step 12.1
=========================
Hinglish: Jaise `tools/base.py` mein `ToolResult` ek FIXED shape hai
jisse Agent/UI/tests consistently parse kar sakein, waise hi yahan
`Issue` aur `InspectionReport` har Inspector ka EXACT same output
shape define karte hain — koi random dict nahi.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class Severity(str, Enum):
    """Hinglish: Har issue ka ek risk level — UI/fixer isse priority decide karta hai."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class Issue:
    """Ek single detected defect — kis object mein, kya problem, kitni severe."""
    object_name: str
    issue_type: str
    severity: Severity
    message: str
    auto_fixable: bool = False

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("Issue.object_name must be a non-empty string")
        if not self.issue_type or not isinstance(self.issue_type, str):
            raise ValueError("Issue.issue_type must be a non-empty string")


@dataclass
class InspectionReport:
    """
    Hinglish: Ek poori inspection run ka result — jitne bhi Inspectors
    chale, unke saare `Issue`s yahan aggregate hote hain.

    `passed` property par nahi, method-jaisa property hai — koi issue
    na ho toh PASS, warna FAIL. Yehi report Copilot UI aur benchmark
    dono ko dikhaya jaata hai.
    """
    issues: List[Issue] = field(default_factory=list)
    retries_used: int = 0

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0

    @property
    def blocking_issues(self) -> List[Issue]:
        """Hinglish: HIGH severity issues — inke saath export nahi hona chahiye."""
        return [issue for issue in self.issues if issue.severity == Severity.HIGH]

    @property
    def unfixable_issues(self) -> List[Issue]:
        return [issue for issue in self.issues if not issue.auto_fixable]

    def to_dict(self) -> dict:
        """Hinglish: UI panel aur benchmark reporter ke liye JSON-serializable form."""
        return {
            "passed": self.passed,
            "retries_used": self.retries_used,
            "issue_count": len(self.issues),
            "issues": [
                {
                    "object_name": issue.object_name,
                    "issue_type": issue.issue_type,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "auto_fixable": issue.auto_fixable,
                }
                for issue in self.issues
            ],
        }
