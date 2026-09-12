"""
Animation Tools — Step 9.13
================================
Hinglish: Keyframe insert karne ke liye Tool interface.
"""

from dataclasses import dataclass
from typing import List, Optional

from .base import Permission, Tool, ToolResult


@dataclass
class InsertKeyframeInput:
    object_name: str
    frame: int
    location: Optional[List[float]] = None

    def __post_init__(self):
        if not self.object_name:
            raise ValueError("InsertKeyframeInput.object_name must be a non-empty string")
        if self.frame < 0:
            raise ValueError("InsertKeyframeInput.frame must be non-negative")
        if self.location is not None and len(self.location) != 3:
            raise ValueError("InsertKeyframeInput.location must have exactly 3 values [x, y, z]")


class InsertKeyframeTool(Tool):
    name = "animation.keyframe"
    description = "Inserts a location keyframe for an object at a given frame."
    permission = Permission.SAFE_WRITE
    input_model = InsertKeyframeInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: InsertKeyframeInput) -> ToolResult:
        success = self._bridge.insert_keyframe(
            object_name=validated_input.object_name,
            frame=validated_input.frame,
            location=validated_input.location,
        )

        if not success:
            return ToolResult.fail(f"Object '{validated_input.object_name}' not found.")

        return ToolResult.ok({
            "object": validated_input.object_name,
            "frame": validated_input.frame,
        })