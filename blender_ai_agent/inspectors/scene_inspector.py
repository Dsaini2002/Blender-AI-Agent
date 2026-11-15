"""SceneInspector"""

from typing import Any, Dict, List


class SceneInspector:
    def __init__(self, bridge):
        self._bridge = bridge

    def inspect(self) -> Dict[str, Any]:
        return {
            "scene": self._inspect_scene(),
            "objects": self._inspect_objects(),
        }

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
        data = {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
        }

        if obj.type == "MESH":
            data["rotation"] = list(obj.rotation_euler)
            data["scale"] = list(obj.scale)

            try:
                mats = getattr(getattr(obj, "data", None), "materials", None)
                names = [m.name for m in mats if m is not None] if mats is not None else []
                if names:
                    data["materials"] = names
            except (TypeError, AttributeError):
                pass

        return data