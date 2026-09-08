"""
Modifier Tools — Step 2.6
============================
Hinglish: Same pattern — har tool `Tool` extend karta hai, `run()`
implement karta hai. ConfigureModifierTool generic properties dict
accept karta hai, kyunki har modifier type ki alag properties hoti hain.
"""

from .base import Permission, Tool, ToolResult
from .models import AddModifierInput, ConfigureModifierInput, RemoveModifierInput


class AddModifierTool(Tool):
    name = "modifier.add"
    description = "Adds a new modifier (e.g. Bevel, Subdivision) to an existing object."
    permission = Permission.SAFE_WRITE
    input_model = AddModifierInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: AddModifierInput) -> ToolResult:
        modifier = self._bridge.add_modifier(
            object_name=validated_input.object_name,
            modifier_name=validated_input.modifier_name,
            modifier_type=validated_input.modifier_type,
        )

        if modifier is None:
            return ToolResult.fail(f"Object '{validated_input.object_name}' not found.")

        return ToolResult.ok({
            "object": validated_input.object_name,
            "modifier": modifier.name,
            "type": modifier.type,
        })


class RemoveModifierTool(Tool):
    name = "modifier.remove"
    description = "Removes a modifier from an existing object."
    permission = Permission.DESTRUCTIVE  # modifier configuration lost ho jaayegi
    input_model = RemoveModifierInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: RemoveModifierInput) -> ToolResult:
        removed = self._bridge.remove_modifier(
            object_name=validated_input.object_name,
            modifier_name=validated_input.modifier_name,
        )

        if not removed:
            return ToolResult.fail(
                f"Could not remove modifier '{validated_input.modifier_name}' from "
                f"'{validated_input.object_name}' — object or modifier not found."
            )

        return ToolResult.ok({
            "object": validated_input.object_name,
            "removed": validated_input.modifier_name,
        })


class ConfigureModifierTool(Tool):
    name = "modifier.configure"
    description = "Updates properties (e.g. width, levels) of an existing modifier."
    permission = Permission.SAFE_WRITE
    input_model = ConfigureModifierInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: ConfigureModifierInput) -> ToolResult:
        modifier = self._bridge.configure_modifier(
            object_name=validated_input.object_name,
            modifier_name=validated_input.modifier_name,
            properties=validated_input.properties,
        )

        if modifier is None:
            return ToolResult.fail(
                f"Could not configure modifier '{validated_input.modifier_name}' on "
                f"'{validated_input.object_name}' — object or modifier not found."
            )

        return ToolResult.ok({
            "object": validated_input.object_name,
            "modifier": modifier.name,
        })