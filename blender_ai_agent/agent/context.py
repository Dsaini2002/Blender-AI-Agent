"""
ContextManager — Step 3.3
============================
Hinglish: LLM ko HAMESHA poori scene nahi bhejni — sirf jo task ke
liye relevant hai. Ye class scene ki full JSON (SceneInspector se)
leke usse ek COMPACT, LLM-friendly summary mein badalti hai.

Abhi ke liye 2 strategies:
  1. Poori scene ka summary (object count, names only — details nahi)
  2. Specific object(s) ka full detail (jab user kisi cheez ka naam le)
"""

from typing import Any, Dict, List, Optional


class ContextManager:
    """
    Hinglish: Constructor mein SceneInspectTool (ya koi bhi object
    jiska `execute({})` scene data de) inject hota hai — Dependency
    Injection, jaisa humesha se karte aaye hain.
    """

    def __init__(self, scene_inspect_tool):
        self._scene_inspect_tool = scene_inspect_tool

    def build_context(self, focus_object_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Hinglish: Agent ke liye ek compact context banata hai.

        Agar `focus_object_names` diya hai (jaise ["Cube"]), toh sirf
        un objects ka FULL detail milega. Agar nahi diya, toh sirf
        summary milega (object count + names) — poora detail nahi.
        """
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
        """Hinglish: Sirf naam aur type — full detail (location/rotation/scale) nahi."""
        return {
            "scene_name": scene_data.get("scene", {}).get("name", "Unknown"),
            "object_count": len(all_objects),
            "objects_summary": [
                {"name": obj["name"], "type": obj["type"]}
                for obj in all_objects
            ],
        }

    def _build_focused_context(self, all_objects: List[Dict], focus_names: List[str]) -> Dict[str, Any]:
        """Hinglish: Sirf named objects ka FULL detail (location, rotation, scale sab)."""
        focused = [obj for obj in all_objects if obj["name"] in focus_names]
        missing = [name for name in focus_names if name not in [obj["name"] for obj in all_objects]]

        return {
            "focused_objects": focused,
            "not_found": missing,
        }