"""
Asset Tools
=============
Hinglish: Ye tool ek LOCAL mesh file (.obj/.fbx/.glb/.gltf) ko scene mein
import karta hai. Ye koi internet download nahi karta - user ko file
pehle se khud disk par rakhni hoti hai (kisi bhi free/CC0 asset site se,
jaise Poly Haven, Sketchfab (CC0 filter), BlenderKit free tier), phir
is tool se uska path diya jaata hai.
"""

from .base import Permission, Tool, ToolResult
from .models import ImportBlendInput, ImportModelInput, ListBlendObjectsInput


class ImportModelTool(Tool):
    name = "asset.import_model"
    description = (
        "Imports an existing LOCAL 3D model file (.obj, .fbx, .glb, or .gltf) from disk "
        "into the current scene. This does NOT download anything from the internet - the "
        "file must already exist at the given filepath on the user's machine. Use this when "
        "the user gives you a file path to a downloaded/exported model, instead of trying to "
        "build a complex object entirely from primitives."
    )
    permission = Permission.SAFE_WRITE
    input_model = ImportModelInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: ImportModelInput) -> ToolResult:
        try:
            imported = self._bridge.import_model(
                filepath=validated_input.filepath,
                name=validated_input.name,
                scale=validated_input.scale,
            )
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        return ToolResult.ok({
            "filepath": validated_input.filepath,
            "imported_objects": [obj.name for obj in imported],
        })


class ListBlendObjectsTool(Tool):
    name = "asset.list_blend_objects"
    description = (
        "Lists the object names inside a LOCAL .blend file, without importing anything. "
        "Unlike .obj/.fbx/.glb (which import their whole scene), a .blend file requires "
        "picking specific named objects to bring in - call this FIRST to see what's "
        "available, then call asset.import_blend with the names you want."
    )
    permission = Permission.READ_ONLY
    input_model = ListBlendObjectsInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: ListBlendObjectsInput) -> ToolResult:
        try:
            names = self._bridge.list_blend_objects(validated_input.filepath)
        except ValueError as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok({"filepath": validated_input.filepath, "objects": names})


class ImportBlendTool(Tool):
    name = "asset.import_blend"
    description = (
        "Appends object(s) from a LOCAL .blend file into the current scene. Pass "
        "object_names (from asset.list_blend_objects) to bring in specific objects, or "
        "omit it to bring in everything in the file. Use name_prefix to avoid name "
        "collisions with objects already in the scene."
    )
    permission = Permission.SAFE_WRITE
    input_model = ImportBlendInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: ImportBlendInput) -> ToolResult:
        try:
            imported = self._bridge.import_blend(
                filepath=validated_input.filepath,
                object_names=validated_input.object_names,
                name_prefix=validated_input.name_prefix,
            )
        except ValueError as exc:
            return ToolResult.fail(str(exc))
        return ToolResult.ok({
            "filepath": validated_input.filepath,
            "imported_objects": [obj.name for obj in imported],
        })