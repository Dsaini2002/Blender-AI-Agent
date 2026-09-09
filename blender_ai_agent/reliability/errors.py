"""
Error Classification — Step 4.6
===================================
Hinglish: Generic "something went wrong" kaafi nahi hai. Har error
ko ek CODE aur "recoverable" flag milta hai — taaki Agent decide kar
sake ki retry/repair try karna sahi hai ya seedha rukna hai.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    OBJECT_NOT_FOUND = "OBJECT_NOT_FOUND"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TIMEOUT = "TIMEOUT"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class ToolError:
    code: ErrorCode
    message: str
    recoverable: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


def classify_tool_error(message: str) -> ToolError:
    """
    Hinglish: Tool.execute() se aaya raw error string leke, ek
    structured ToolError banata hai. Simple keyword-matching hai —
    future mein zaroorat pade toh zyada precise bana sakte hain.
    """
    lowered = (message or "").lower()

    if "not found" in lowered:
        return ToolError(code=ErrorCode.OBJECT_NOT_FOUND, message=message, recoverable=True)
    if "invalid input" in lowered or "must be" in lowered or "must have" in lowered:
        return ToolError(code=ErrorCode.INVALID_INPUT, message=message, recoverable=False)
    if "unknown tool" in lowered:
        return ToolError(code=ErrorCode.TOOL_EXECUTION_FAILED, message=message, recoverable=False)

    return ToolError(code=ErrorCode.UNKNOWN_ERROR, message=message, recoverable=False)


def classify_validation_error(reasons: List[str]) -> ToolError:
    """Hinglish: Validator ke fail hone par (tool succeed hua tha, par scene galat thi)."""
    message = "; ".join(reasons)
    return ToolError(code=ErrorCode.VALIDATION_FAILED, message=message, recoverable=True)