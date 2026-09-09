"""
Vision Error Classification — Step 5.15
============================================
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class VisionErrorCode(str, Enum):
    IMAGE_CAPTURE_FAILED = "IMAGE_CAPTURE_FAILED"
    VISION_PROVIDER_FAILED = "VISION_PROVIDER_FAILED"
    INVALID_IMAGE = "INVALID_IMAGE"
    VISION_TIMEOUT = "VISION_TIMEOUT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    OBJECT_NOT_IDENTIFIED = "OBJECT_NOT_IDENTIFIED"
    VISUAL_VALIDATION_FAILED = "VISUAL_VALIDATION_FAILED"


class VisionError(Exception):
    def __init__(self, code: VisionErrorCode, message: str, recoverable: bool = False, details: Dict[str, Any] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.details = details or {}


def classify_vision_exception(exc: Exception) -> VisionError:
    message = str(exc)
    lowered = message.lower()

    if "timeout" in lowered:
        return VisionError(VisionErrorCode.VISION_TIMEOUT, message, recoverable=True)
    if "no scripted observation" in lowered or "provider" in lowered:
        return VisionError(VisionErrorCode.VISION_PROVIDER_FAILED, message, recoverable=True)
    if "image" in lowered or "capture" in lowered:
        return VisionError(VisionErrorCode.IMAGE_CAPTURE_FAILED, message, recoverable=True)

    return VisionError(VisionErrorCode.VISION_PROVIDER_FAILED, message, recoverable=False)


def check_confidence(observation, min_confidence: float = 0.5) -> None:
    if observation.confidence < min_confidence:
        raise VisionError(
            VisionErrorCode.LOW_CONFIDENCE,
            f"Observation confidence {observation.confidence} is below threshold {min_confidence}.",
            recoverable=False,
            details={"confidence": observation.confidence, "threshold": min_confidence},
        )