"""CopilotContext
==============

    Blender -> SceneInspector -> CopilotContext
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CopilotContext:
    selected_objects: List[str] = field(default_factory=list)
    active_object: Optional[str] = None
    active_camera: Optional[str] = None
    current_scene: Optional[str] = None


class CopilotContextBuilder:

    def __init__(self, bridge):
        self._bridge = bridge

    def build(self, selected_object_names: List[str] = None) -> CopilotContext:
        selected = selected_object_names or []
        active_object = selected[0] if selected else None

        active_camera = self._find_active_camera()
        scene_name = self._bridge.get_scene_name()

        return CopilotContext(
            selected_objects=selected,
            active_object=active_object,
            active_camera=active_camera,
            current_scene=scene_name,
        )

    def _find_active_camera(self) -> Optional[str]:
        for obj in self._bridge.get_objects():
            if obj.type == "CAMERA":
                return obj.name
        return None