"""VisualObservation model"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class VisualObservation:
    description: str
    objects_detected: List[str] = field(default_factory=list)
    composition: Dict[str, Any] = field(default_factory=dict)
    lighting: Dict[str, Any] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    confidence: float = 1.0

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError("VisualObservation.confidence must be between 0.0 and 1.0")

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < 0.5