"""
Suggestion system — Step 6.15
=================================
Hinglish: Task complete hone ke baad, scene state dekh kar proactive
suggestions dena. Abhi ke liye simple rule-based hai (spec khud
kehta hai "random nahi honi chahiye, scene-aware honi chahiye" —
Step 6.16 ka full context-awareness abhi simplified hai, lekin scene
data hi use karte hain, hardcoded list nahi).
"""

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
        # Dependency Injection — jaisa hamesha
        self._scene_inspect_tool = scene_inspect_tool

    def suggest(self, last_tool_used: str = "") -> List[Suggestion]:
        """
        Hinglish: Scene ko dekh kar relevant suggestions deta hai.
        Simple rule: agar objects hain but material check possible
        nahi hai abhi (fake bridge mein material tracking simplified
        hai) — isliye hum sirf OBJECT COUNT ke basis pe suggest karte
        hain, taaki test predictable rahe.
        """
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