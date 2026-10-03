"""
Mesh Tools
===========
Hinglish: Primitives (cube, cone, sphere...) se jo shape nahi banta — jaise tent ka triangle, wedge, chhat, ramp —
wo ab vertices + faces dekar seedha bana sakte hain.
"""

from .base import Permission, Tool, ToolResult
from .models import CreateMeshInput, DamageMeshInput


class CreateMeshTool(Tool):
    name = "mesh.create"
    description = (
        "Creates a custom mesh from vertices and faces - use it for shapes the primitives cannot make: a "
        "triangle, wedge, gable end, roof, ramp, pyramid, a flat panel. vertices = [[x,y,z], ...]; faces = "
        "lists of vertex INDEXES (0-based), 3+ per face, e.g. a triangle: vertices [[0,0,0],[1,0,0],[0,0,1]], "
        "faces [[0,1,2]]; a square panel: 4 vertices, faces [[0,1,2,3]]; a pyramid: 4 base + 1 top vertex, faces "
        "[[0,1,2,3],[0,1,4],[1,2,4],[2,3,4],[3,0,4]]. Position it with location/rotation/scale, then colour it with "
        "material.create + material.assign. shade_smooth=true for rounded shading."
    )
    permission = Permission.SAFE_WRITE
    input_model = CreateMeshInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: CreateMeshInput) -> ToolResult:
        obj = self._bridge.create_mesh(
            name=validated_input.name,
            vertices=validated_input.vertices,
            faces=validated_input.faces,
            location=validated_input.location,
            rotation=validated_input.rotation,
            scale=validated_input.scale,
            shade_smooth=validated_input.shade_smooth,
        )
        return ToolResult.ok({
            "name": obj.name,
            "vertex_count": len(validated_input.vertices),
            "face_count": len(validated_input.faces),
            "location": list(obj.location),
        })


class DamageMeshTool(Tool):
    name = "mesh.damage"
    description = (
        "Makes part of an existing mesh look damaged. Use it when the user asks for a BROKEN / chipped / cracked / "
        "dented / worn look on an object (including imported models): e.g. 'the top of the bottle should look a little "
        "broken' -> object_name=<bottle>, region='top', style='broken'. region: top, bottom, left, right, front, back or "
        "all (neck/lid/rim = top, base = bottom). style: broken (jagged rim with shards and missing pieces), chipped (small "
        "chips), dented (pressed in), rough (worn, bumpy). portion = how much of the object's height/width is affected "
        "(0.25 = top quarter), strength = how damaged (0.1 slight, 0.3 heavy). Works on a mesh or on an imported "
        "model's root (all its meshes). Keeps UVs and materials. Same seed gives the same result; change seed for a "
        "different break."
    )
    permission = Permission.SAFE_WRITE
    input_model = DamageMeshInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: DamageMeshInput) -> ToolResult:
        result = self._bridge.damage_mesh(
            object_name=validated_input.object_name,
            region=validated_input.region,
            portion=validated_input.portion,
            strength=validated_input.strength,
            style=validated_input.style,
            seed=validated_input.seed,
            detail=validated_input.detail,
        )
        if result is None:
            return ToolResult.fail(
                f"Object '{validated_input.object_name}' not found, or it has no mesh to damage."
            )
        return ToolResult.ok({"style": validated_input.style, "region": validated_input.region, **result})