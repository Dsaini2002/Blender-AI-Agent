"""ContextManager"""

from typing import Any, Dict, List, Optional


class ContextManager:

    def __init__(self, scene_inspect_tool):
        self._scene_inspect_tool = scene_inspect_tool

    def build_context(self, focus_object_names: Optional[List[str]] = None) -> Dict[str, Any]:
        result = self._scene_inspect_tool.execute({})

        if not result.success:
            return {"error": result.error, "objects": []}

        scene_data = result.data
        all_objects = scene_data.get("objects", [])

        if focus_object_names:
            return self._build_focused_context(all_objects, focus_object_names)

        return self._build_summary_context(scene_data, all_objects)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _build_summary_context(self, scene_data: Dict[str, Any], all_objects: List[Dict]) -> Dict[str, Any]:
        return {
            "scene_name": scene_data.get("scene", {}).get("name", "Unknown"),
            "object_count": len(all_objects),
            "objects_summary": [
                {"name": obj["name"], "type": obj["type"]}
                for obj in all_objects
            ],
        }

    def _build_focused_context(self, all_objects: List[Dict], focus_names: List[str]) -> Dict[str, Any]:
        focused = [obj for obj in all_objects if obj["name"] in focus_names]
        missing = [name for name in focus_names if name not in [obj["name"] for obj in all_objects]]

        return {
            "focused_objects": focused,
            "not_found": missing,
        }

    def build_context_text(self) -> str:
        result = self._scene_inspect_tool.execute({})
        if not result.success:
            return ""

        objects = result.data.get("objects", [])
        if not objects:
            return "The scene currently has no objects."

        lines = ["Current scene objects (use these exact names and positions when referencing existing objects):"]
        for obj in objects:
            loc = obj.get("location", [0, 0, 0])
            line = f"- {obj['name']} (type={obj['type']}, location=({loc[0]:.2f}, {loc[1]:.2f}, {loc[2]:.2f})"
            if "scale" in obj:
                scale = obj["scale"]
                line += f", scale=({scale[0]:.2f}, {scale[1]:.2f}, {scale[2]:.2f})"
            line += ")"
            if obj.get("materials"):
                line += f" material={', '.join(obj['materials'])}"
            lines.append(line)

        return "\n".join(lines)