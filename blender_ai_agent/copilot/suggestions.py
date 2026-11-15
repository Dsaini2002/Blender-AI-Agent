"""Suggestion system"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Suggestion:
    title: str
    action: str
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SuggestionEngine:

    def __init__(self, scene_inspect_tool):
        self._scene_inspect_tool = scene_inspect_tool

    def suggest(self, last_tool_used: str = "") -> List[Suggestion]:
        result = self._scene_inspect_tool.execute({})
        if not result.success:
            return []

        objects = result.data.get("objects", [])

        if not objects:
            return [Suggestion(title="Create an object", action="object.create")]

        suggestions = [
            Suggestion(title="Add material", action="material.create"),
            Suggestion(title="Add bevel", action="modifier.add"),
        ]

        has_camera = any(obj["type"] == "CAMERA" for obj in objects)
        if not has_camera:
            suggestions.append(Suggestion(title="Add a camera", action="camera.create"))
        else:
            suggestions.append(Suggestion(title="Check camera framing", action="vision.observe"))

        return suggestions