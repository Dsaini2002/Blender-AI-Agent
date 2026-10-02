"""
Retopology Tools
=================
Hinglish: Dense / messy mesh (sculpt, import, boolean ke baad) ko clean,
kam-poly topology mein badalne ke tools. Rule wahi — raw bpy yahan nahi,
sirf BlenderBridge ke through.

Safety: retopology.remesh original ko kabhi overwrite nahi karta; wo
hamesha ek NAYI copy banata hai. Isliye SAFE_WRITE hai, aur TransactionManager
rollback sirf naya object delete karke poora undo kar sakta hai.
"""

from .base import Permission, Tool, ToolResult
from .models import AnalyzeTopologyInput, RetopologyInput


class AnalyzeTopologyTool(Tool):
    name = "retopology.analyze"
    description = (
        "Reads a mesh object's topology quality: face count, triangles/quads/n-gons, "
        "quad ratio (1.0 = all quads) and pole count (vertices that are not valence 4). "
        "Call this BEFORE retopology.remesh to decide if retopology is needed, and AFTER "
        "to confirm the result improved."
    )
    permission = Permission.READ_ONLY
    input_model = AnalyzeTopologyInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: AnalyzeTopologyInput) -> ToolResult:
        stats = self._bridge.get_topology_stats(validated_input.object_name)

        if stats is None:
            return ToolResult.fail(f"Object '{validated_input.object_name}' not found or not a mesh.")

        return ToolResult.ok({"object_name": validated_input.object_name, **stats})


class RetopologyTool(Tool):
    name = "retopology.remesh"
    description = (
        "Retopologizes a mesh into a cleaner, lower-poly mesh. Creates a NEW object "
        "(default '<name>_retopo') and hides the original, so nothing is lost. "
        "method QUADRIFLOW (default): clean quad-dominant flow, set target_faces "
        "(e.g. 2000) - best for characters/props that will be subdivided, rigged or animated. "
        "method VOXEL: even uniform topology, set voxel_size (smaller = denser) - good for "
        "fixing messy/non-manifold meshes before sculpting. "
        "method DECIMATE: only reduces polygon count by decimate_ratio (0-1), keeps shape "
        "but gives triangles - good for background props / game LODs. "
        "Use retopology.analyze first to check the current face count."
    )
    permission = Permission.SAFE_WRITE
    input_model = RetopologyInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: RetopologyInput) -> ToolResult:
        # Hinglish: Bridge ValueError/RuntimeError raise karta hai agar Blender
        # ka operator cancel ho — Tool.execute() use ToolResult.fail mein badal deta hai.
        result = self._bridge.retopologize(
            object_name=validated_input.object_name,
            method=validated_input.method,
            target_faces=validated_input.target_faces,
            voxel_size=validated_input.voxel_size,
            decimate_ratio=validated_input.decimate_ratio,
            preserve_sharp=validated_input.preserve_sharp,
            smooth_normals=validated_input.smooth_normals,
            new_name=validated_input.new_name,
            hide_original=validated_input.hide_original,
        )

        if result is None:
            return ToolResult.fail(
                f"Object '{validated_input.object_name}' not found or not a mesh."
            )

        before, after = result["before"], result["after"]
        return ToolResult.ok({
            "source": validated_input.object_name,
            "new_object": result["new_name"],
            "method": result["method"],
            "faces_before": before["face_count"],
            "faces_after": after["face_count"],
            "quad_ratio_before": round(before["quad_ratio"], 3),
            "quad_ratio_after": round(after["quad_ratio"], 3),
            "poles_before": before["pole_count"],
            "poles_after": after["pole_count"],
        })
