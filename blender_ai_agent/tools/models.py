"""
Input/Output Models — Step 2.2
================================
Hinglish: Ab hum random dict ki jagah TYPED dataclasses use karenge
har tool ke input/output ke liye. Isse:
  - IDE autocomplete milega
  - Galat field naam likhne pe turant error aayega (runtime pe)
  - Har tool ka "contract" explicitly document ho jaata hai

Naming convention: <ToolPurpose>Input, jaise CreateObjectInput.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CreateObjectInput:
    """
    Hinglish: object.create tool (Step 2.4) ke liye input contract.

    Required field: name
    Optional fields: sensible defaults ke saath — user/Agent ko sab
    kuch specify karne ki zaroorat nahi.
    """
    name: str
    object_type: str = "MESH"
    primitive: str = "CUBE"
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def __post_init__(self):
        # Hinglish: dataclass khud type-check nahi karta (Python dataclasses
        # sirf structure define karte hain), isliye zaroori validation
        # manually likhni padti hai.
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CreateObjectInput.name must be a non-empty string")
        if len(self.location) != 3:
            raise ValueError("CreateObjectInput.location must have exactly 3 values [x, y, z]")


@dataclass
class DeleteObjectInput:
    """object.delete tool (Step 2.4) ke liye input contract."""
    name: str

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("DeleteObjectInput.name must be a non-empty string")