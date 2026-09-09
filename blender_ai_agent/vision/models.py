"""
VisualObservation model — Step 5.1 / 5.3
============================================
Hinglish: Vision provider ka output ek random string/paragraph nahi
hoga — ek TYPED, structured model hoga. Jaisa humne LLM ke liye
ModelResponse banaya tha, waisa hi vision ke liye.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class VisualObservation:
    """
    Hinglish: Ek image ko "dekhne" ka structured result.

    `confidence` important hai — Step 5.16 ke spec ke hisaab se,
    vision output ko "absolute truth" nahi maanna — kam confidence
    wale observations pe destructive action nahi lena chahiye.
    """
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
        """Hinglish: Threshold — 0.5 se kam confidence ko 'unreliable' maanenge."""
        return self.confidence < 0.5