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
from .models import ImportModelInput


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