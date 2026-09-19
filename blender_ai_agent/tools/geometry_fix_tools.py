"""
Geometry Fix Tools — Step 12.4
==================================
Hinglish: Phase 12 ke QA layer ke liye "Astra" jaisa auto-fixer koi
naya raw-bpy hack nahi hai — jaisa baaki poore codebase mein rule
hai, "BlenderBridge = sole bpy touchpoint", waise hi yahan bhi fixes
NORMAL Tool system ke through hi hote hain, permission-gated.
"""

from .base import Permission, Tool, ToolResult
from .models import RecalculateNormalsInput, SeparateOverlapInput


class RecalculateNormalsTool(Tool):
    name = "geometry.recalculate_normals"
    description = "Recalculates (outward) face normals for a mesh object — fixes flipped-normal issues."
    permission = Permission.SAFE_WRITE
    input_model = RecalculateNormalsInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: RecalculateNormalsInput) -> ToolResult:
        success = self._bridge.recalculate_normals(validated_input.object_name)

        if not success:
            return ToolResult.fail(f"Object '{validated_input.object_name}' not found or not a mesh.")

        return ToolResult.ok({"object_name": validated_input.object_name, "fixed": "flipped_normals"})


class SeparateOverlapTool(Tool):
    name = "geometry.separate_overlap"
    description = "Nudges an object by an offset to resolve a bounding-box overlap with another object."
    permission = Permission.SAFE_WRITE
    input_model = SeparateOverlapInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: SeparateOverlapInput) -> ToolResult:
        obj = self._bridge.get_object(validated_input.object_name)
        if obj is None:
            return ToolResult.fail(f"Object '{validated_input.object_name}' not found in scene.")

        current_location = list(obj.location)
        new_location = [
            current_location[i] + validated_input.offset[i] for i in range(3)
        ]

        self._bridge.transform_object(validated_input.object_name, location=new_location)

        return ToolResult.ok({
            "object_name": validated_input.object_name,
            "fixed": "intersecting_geometry",
            "new_location": new_location,
        })
