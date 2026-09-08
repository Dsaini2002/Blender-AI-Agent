"""
SceneInspectTool
=================
Hinglish: SceneInspector ko ek "Tool" ke roop mein expose karta hai,
taaki future mein LLM/Agent isko uniform tarike se call kar sake.
"""

from typing import Any, Dict

from .base import Tool


class SceneInspectTool(Tool):
    name = "scene.inspect"
    description = "Returns structured JSON state of the current Blender scene."

    def __init__(self, inspector):
        # Dependency Injection: SceneInspector bahar se diya gaya hai.
        self._inspector = inspector

    def execute(self, input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        return self._inspector.inspect()