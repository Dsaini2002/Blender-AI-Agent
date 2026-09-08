"""
Input/Output Models — Step 2.2 + 2.4
======================================
Hinglish: Har tool ka input ek typed dataclass hai — random dict nahi.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CreateObjectInput:
    """object.create tool ke liye input contract."""
    name: str
    object_type: str = "MESH"
    primitive: str = "CUBE"
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CreateObjectInput.name must be a non-empty string")
        if len(self.location) != 3:
            raise ValueError("CreateObjectInput.location must have exactly 3 values [x, y, z]")


@dataclass
class DeleteObjectInput:
    """object.delete tool ke liye input contract."""
    name: str

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("DeleteObjectInput.name must be a non-empty string")


@dataclass
class DuplicateObjectInput:
    """object.duplicate tool ke liye input contract."""
    name: str
    new_name: str = ""

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("DuplicateObjectInput.name must be a non-empty string")


@dataclass
class RenameObjectInput:
    """object.rename tool ke liye input contract."""
    old_name: str
    new_name: str

    def __post_init__(self):
        if not self.old_name or not isinstance(self.old_name, str):
            raise ValueError("RenameObjectInput.old_name must be a non-empty string")
        if not self.new_name or not isinstance(self.new_name, str):
            raise ValueError("RenameObjectInput.new_name must be a non-empty string")


@dataclass
class TransformObjectInput:
    """object.transform tool ke liye input contract."""
    name: str
    location: Optional[List[float]] = None
    rotation: Optional[List[float]] = None
    scale: Optional[List[float]] = None

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("TransformObjectInput.name must be a non-empty string")

        for field_name, value in (
            ("location", self.location),
            ("rotation", self.rotation),
            ("scale", self.scale),
        ):
            if value is not None and len(value) != 3:
                raise ValueError(f"TransformObjectInput.{field_name} must have exactly 3 values [x, y, z]")

        if self.location is None and self.rotation is None and self.scale is None:
            raise ValueError("TransformObjectInput requires at least one of: location, rotation, scale")