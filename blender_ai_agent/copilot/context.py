"""
CopilotContext — Step 6.18
==============================
Hinglish: Selection/active object/camera ka awareness — lekin
IMPORTANT: ye khud "source of truth" nahi hai, Blender state se
DERIVE hota hai har baar. Independent truth maintain nahi karte
(jaisa spec kehta hai) — warna state drift ho sakti hai.

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
    """Hinglish: Bridge se fresh CopilotContext banata hai — har baar naya, kabhi cache nahi karta."""

    def __init__(self, bridge):
        self._bridge = bridge

    def build(self, selected_object_names: List[str] = None) -> CopilotContext:
        """
        Hinglish: `selected_object_names` UI se aata hai (Blender ka
        selection state) — humari FakeBridge/BlenderBridge khud
        "selection" track nahi karti abhi, isliye ye explicitly UI
        se pass hota hai. `active_object` isi list ka pehla item maana
        jaata hai (simplification).
        """
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