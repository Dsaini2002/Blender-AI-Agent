"""Error Classification"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List


class ErrorCode(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    MISSING_ARGUMENT = "MISSING_ARGUMENT"
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
    lowered = (message or "").lower()

    if "not found" in lowered:
        return ToolError(code=ErrorCode.OBJECT_NOT_FOUND, message=message, recoverable=True)
    if "missing" in lowered and "required" in lowered and "argument" in lowered:
        return ToolError(code=ErrorCode.MISSING_ARGUMENT, message=message, recoverable=True)
    if "invalid input" in lowered or "must be" in lowered or "must have" in lowered:
        return ToolError(code=ErrorCode.INVALID_INPUT, message=message, recoverable=False)
    if "unknown tool" in lowered:
        return ToolError(code=ErrorCode.TOOL_EXECUTION_FAILED, message=message, recoverable=False)

    return ToolError(code=ErrorCode.UNKNOWN_ERROR, message=message, recoverable=False)


def classify_validation_error(reasons: List[str]) -> ToolError:
    message = "; ".join(reasons)
    return ToolError(code=ErrorCode.VALIDATION_FAILED, message=message, recoverable=True)