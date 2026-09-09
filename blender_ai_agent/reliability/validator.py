"""
Validator (abstract base class) — Step 4.1
==============================================
Hinglish: Tool ka ToolResult.success sirf itna batata hai ki tool
CRASH nahi hua. Lekin ye guarantee nahi karta ki Blender scene mein
ACTUALLY wahi hua jo hona chahiye tha.

    Tool response ≠ truth
    Blender scene = source of truth

Validator scene ko dobara check karke confirm karta hai ki expected
outcome fact mein hua ya nahi.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class ValidationResult:
    """
    Hinglish: ToolResult jaisa hi pattern — consistent shape, taaki
    caller ko hamesha same tarike se result padhna aaye.
    """
    valid: bool
    reasons: List[str] = field(default_factory=list)

    @staticmethod
    def ok() -> "ValidationResult":
        return ValidationResult(valid=True)

    @staticmethod
    def failed(*reasons: str) -> "ValidationResult":
        return ValidationResult(valid=False, reasons=list(reasons))


class Validator(ABC):
    """
    Hinglish: Har concrete validator (ObjectValidator, MaterialValidator,
    TransformValidator — Step 4.2 mein) isko extend karega.

    `expected` = tool ko jo input diya gaya tha (ya jo outcome expect
                 kiya gaya tha)
    `bridge`   = current Blender state padhne ke liye (source of truth)
    """

    @abstractmethod
    def validate(self, expected: Dict[str, Any], bridge) -> ValidationResult:
        raise NotImplementedError