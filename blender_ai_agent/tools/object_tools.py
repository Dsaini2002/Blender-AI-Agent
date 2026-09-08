"""
Object Tools — Step 2.4
=========================
Hinglish: Ye Phase 2 ke "write" tools hain. Har tool `Tool` extend
karta hai, sabka `execute()` same hai (base class se), lekin `run()`
ka andar ka kaam bilkul alag hai — yahi POLYMORPHISM hai.
"""

from .base import Permission, Tool, ToolResult
from .models import (
    CreateObjectInput,
    DeleteObjectInput,
    DuplicateObjectInput,
    RenameObjectInput,
    TransformObjectInput,
)


class CreateObjectTool(Tool):
    name = "object.create"
    description = "Creates a new object (e.g. cube, sphere) in the scene."
    permission = Permission.SAFE_WRITE
    input_model = CreateObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: CreateObjectInput) -> ToolResult:
        obj = self._bridge.create_object(
            name=validated_input.name,
            object_type=validated_input.object_type,
            primitive=validated_input.primitive,
            location=validated_input.location,
        )
        return ToolResult.ok({
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
        })


class DeleteObjectTool(Tool):
    name = "object.delete"
    description = "Deletes an object from the scene by name."
    permission = Permission.DESTRUCTIVE
    input_model = DeleteObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: DeleteObjectInput) -> ToolResult:
        deleted = self._bridge.delete_object(validated_input.name)

        if not deleted:
            return ToolResult.fail(f"Object '{validated_input.name}' not found in scene.")

        return ToolResult.ok({"deleted": validated_input.name})


class DuplicateObjectTool(Tool):
    name = "object.duplicate"
    description = "Duplicates an existing object in the scene."
    permission = Permission.SAFE_WRITE
    input_model = DuplicateObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: DuplicateObjectInput) -> ToolResult:
        new_obj = self._bridge.duplicate_object(
            name=validated_input.name,
            new_name=validated_input.new_name or None,
        )

        if new_obj is None:
            return ToolResult.fail(f"Object '{validated_input.name}' not found in scene.")

        return ToolResult.ok({
            "original": validated_input.name,
            "duplicate": new_obj.name,
        })


class RenameObjectTool(Tool):
    name = "object.rename"
    description = "Renames an existing object in the scene."
    permission = Permission.SAFE_WRITE
    input_model = RenameObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: RenameObjectInput) -> ToolResult:
        obj = self._bridge.rename_object(validated_input.old_name, validated_input.new_name)

        if obj is None:
            return ToolResult.fail(f"Object '{validated_input.old_name}' not found in scene.")

        return ToolResult.ok({"old_name": validated_input.old_name, "new_name": obj.name})


class TransformObjectTool(Tool):
    name = "object.transform"
    description = "Updates location, rotation, and/or scale of an existing object."
    permission = Permission.SAFE_WRITE
    input_model = TransformObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: TransformObjectInput) -> ToolResult:
        obj = self._bridge.transform_object(
            name=validated_input.name,
            location=validated_input.location,
            rotation=validated_input.rotation,
            scale=validated_input.scale,
        )

        if obj is None:
            return ToolResult.fail(f"Object '{validated_input.name}' not found in scene.")

        return ToolResult.ok({
            "name": obj.name,
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
        })