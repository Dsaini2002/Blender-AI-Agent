"""
Material Tools — Step 2.5
============================
Hinglish: Object Tools jaisa hi pattern — har tool `Tool` extend
karta hai, `run()` implement karta hai. Yahan bhi POLYMORPHISM hai:
3 alag tools, same `execute()` interface.
"""

from .base import Permission, Tool, ToolResult
from .models import AssignMaterialInput, CreateMaterialInput, ModifyMaterialInput


class CreateMaterialTool(Tool):
    name = "material.create"
    description = "Creates a new material, optionally with a base color."
    permission = Permission.SAFE_WRITE
    input_model = CreateMaterialInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: CreateMaterialInput) -> ToolResult:
        material = self._bridge.create_material(
            name=validated_input.name,
            color=validated_input.color,
        )
        return ToolResult.ok({"name": material.name})


class AssignMaterialTool(Tool):
    name = "material.assign"
    description = "Assigns an existing material to an existing object."
    permission = Permission.SAFE_WRITE
    input_model = AssignMaterialInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: AssignMaterialInput) -> ToolResult:
        assigned = self._bridge.assign_material(
            object_name=validated_input.object_name,
            material_name=validated_input.material_name,
        )

        if not assigned:
            return ToolResult.fail(
                f"Could not assign '{validated_input.material_name}' to "
                f"'{validated_input.object_name}' — object or material not found."
            )

        return ToolResult.ok({
            "object": validated_input.object_name,
            "material": validated_input.material_name,
        })


class ModifyMaterialTool(Tool):
    name = "material.modify"
    description = "Updates color, roughness, and/or metallic on an existing material."
    permission = Permission.SAFE_WRITE
    input_model = ModifyMaterialInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: ModifyMaterialInput) -> ToolResult:
        material = self._bridge.modify_material(
            name=validated_input.name,
            color=validated_input.color,
            roughness=validated_input.roughness,
            metallic=validated_input.metallic,
        )

        if material is None:
            return ToolResult.fail(f"Material '{validated_input.name}' not found.")

        return ToolResult.ok({"name": material.name})