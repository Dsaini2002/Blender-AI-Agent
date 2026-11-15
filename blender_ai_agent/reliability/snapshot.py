"""SceneSnapshot"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ObjectSnapshot:
    name: str
    type: str
    location: List[float]
    rotation: List[float]
    scale: List[float]
    modifiers: Optional[List[str]] = None
    material: Optional[str] = None
    uid: Optional[int] = None          # Blender's session_uid: the same object even after a rename


def _modifier_names(obj) -> Optional[List[str]]:
    modifiers = getattr(obj, "modifiers", None)
    if modifiers is None:
        return None
    try:
        return [m.name for m in modifiers]
    except TypeError:
        inner = getattr(modifiers, "_modifiers", None)          # test fakes
        return [m.name for m in inner] if inner is not None else None


def _material_name(obj) -> Optional[str]:
    try:
        slots = getattr(obj, "material_slots", None)
        if slots is not None:
            return slots[0].material.name if len(slots) and slots[0].material else None
    except Exception:  # noqa: BLE001
        return None
    return getattr(obj, "material_name", None)


@dataclass
class SceneSnapshot:
    objects: List[ObjectSnapshot] = field(default_factory=list)

    def get_object(self, name: str) -> Optional[ObjectSnapshot]:
        for obj in self.objects:
            if obj.name == name:
                return obj
        return None

    def object_names(self) -> List[str]:
        return [obj.name for obj in self.objects]

    def by_uid(self, uid) -> Optional[ObjectSnapshot]:
        if uid is None:
            return None
        for obj in self.objects:
            if obj.uid == uid:
                return obj
        return None


class SnapshotManager:

    def __init__(self, bridge):
        self._bridge = bridge

    def capture(self) -> SceneSnapshot:
        objects = []
        def _read():
            for obj in self._bridge.get_objects():
                uid = getattr(obj, "session_uid", None)
                objects.append(ObjectSnapshot(
                    name=obj.name,
                    type=obj.type,
                    location=list(obj.location),
                    rotation=list(obj.rotation_euler),
                    scale=list(obj.scale),
                    modifiers=_modifier_names(obj),
                    material=_material_name(obj),
                    uid=uid if isinstance(uid, int) else None,
                ))
        from ..bridge.main_thread_dispatch import run_on_main_thread
        run_on_main_thread(_read)                  # bpy data is read on Blender's main thread only
        return SceneSnapshot(objects=objects)