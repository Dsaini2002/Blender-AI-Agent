"""
SceneInspectTool — Phase 2 upgrade
====================================
Hinglish: Ab `run()` implement karta hai (execute() nahi — wo base class
mein hai), aur ToolResult return karta hai (raw dict nahi).
"""

from typing import Any, Dict

from .base import Permission, Tool, ToolResult


class SceneInspectTool(Tool):
    name = "scene.inspect"
    description = "Returns structured JSON state of the current Blender scene."
    permission = Permission.READ_ONLY  # kuch modify nahi karta
    input_model = None                 # koi input required nahi

    def __init__(self, inspector):
        # Dependency Injection: SceneInspector bahar se diya gaya hai.
        self._inspector = inspector

    def run(self, validated_input: Dict[str, Any]) -> ToolResult:
        scene_data = self._inspector.inspect()
        return ToolResult.ok(scene_data)