"""
Geometry Node Tools — Step 9.8
===================================
Hinglish: Geometry Nodes ko first-class Tool interface milta hai —
same pattern jo modifier_tools.py mein tha.
"""

from dataclasses import dataclass

from .base import Permission, Tool, ToolResult


@dataclass
class CreateGeometryNodesInput:
    object_name: str
    node_group_name: str

    def __post_init__(self):
        if not self.object_name:
            raise ValueError("CreateGeometryNodesInput.object_name must be a non-empty string")
        if not self.node_group_name:
            raise ValueError("CreateGeometryNodesInput.node_group_name must be a non-empty string")


class CreateGeometryNodesTool(Tool):
    name = "geometry_nodes.create"
    description = "Adds a new Geometry Nodes modifier and node group to an object."
    permission = Permission.SAFE_WRITE
    input_model = CreateGeometryNodesInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: CreateGeometryNodesInput) -> ToolResult:
        modifier = self._bridge.add_geometry_nodes(
            object_name=validated_input.object_name,
            node_group_name=validated_input.node_group_name,
        )

        if modifier is None:
            return ToolResult.fail(f"Object '{validated_input.object_name}' not found.")

        return ToolResult.ok({
            "object": validated_input.object_name,
            "node_group": validated_input.node_group_name,
        })