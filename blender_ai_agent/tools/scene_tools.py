"""SceneInspectTool"""

from typing import Any, Dict

from .base import Permission, Tool, ToolResult


class SceneInspectTool(Tool):
    name = "scene.inspect"
    description = "Returns structured JSON state of the current Blender scene."
    permission = Permission.READ_ONLY
    input_model = None

    def __init__(self, inspector):
        self._inspector = inspector

    def run(self, validated_input: Dict[str, Any]) -> ToolResult:
        scene_data = self._inspector.inspect()
        return ToolResult.ok(scene_data)