"""
SceneInspector
==============
Hinglish: Ye class Blender scene ko "samajhti" hai aur ek clean,
structured (JSON-serializable) representation banati hai.
"""

from typing import Any, Dict, List


class SceneInspector:
    def __init__(self, bridge):
        # Dependency Injection: bridge bahar se pass ki gayi hai, khud nahi banayi.
        self._bridge = bridge

    def inspect(self) -> Dict[str, Any]:
        """Poori scene ki structured state return karta hai."""
        return {
            "scene": self._inspect_scene(),
            "objects": self._inspect_objects(),
        }

    # ---------------------------------------------------------
    # Private helpers (implementation details, bahar se hide)
    # ---------------------------------------------------------
    def _inspect_scene(self) -> Dict[str, Any]:
        return {
            "name": self._bridge.get_scene_name(),
        }

    def _inspect_objects(self) -> List[Dict[str, Any]]:
        result = []
        for obj in self._bridge.get_objects():
            result.append(self._describe_object(obj))
        return result

    def _describe_object(self, obj) -> Dict[str, Any]:
        """Ek single Blender object ko dict mein convert karta hai."""
        data = {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
        }

        # Sirf MESH type objects ke liye extra detail
        if obj.type == "MESH":
            data["rotation"] = list(obj.rotation_euler)
            data["scale"] = list(obj.scale)

        return data