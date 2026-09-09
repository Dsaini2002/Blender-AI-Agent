"""
SceneSnapshot — Step 4.3
============================
Hinglish: Rollback ke liye pehle scene ki "photo" leni padti hai —
taaki operation fail hone par wapas isi state par laut sakein.

Snapshot mein sirf RELEVANT info hoti hai (naam, type, location,
rotation, scale) — poora internal Blender state nahi. Spec khud
kehta hai: "unnecessarily gigantic nahi banana."
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ObjectSnapshot:
    """Ek single object ki state, snapshot ke waqt."""
    name: str
    type: str
    location: List[float]
    rotation: List[float]
    scale: List[float]


@dataclass
class SceneSnapshot:
    """Poori scene ki state, ek point-in-time par."""
    objects: List[ObjectSnapshot] = field(default_factory=list)

    def get_object(self, name: str) -> Optional[ObjectSnapshot]:
        for obj in self.objects:
            if obj.name == name:
                return obj
        return None

    def object_names(self) -> List[str]:
        return [obj.name for obj in self.objects]


class SnapshotManager:
    """Hinglish: Bridge se current scene padh kar SceneSnapshot banata hai."""

    def __init__(self, bridge):
        self._bridge = bridge

    def capture(self) -> SceneSnapshot:
        objects = []
        for obj in self._bridge.get_objects():
            objects.append(ObjectSnapshot(
                name=obj.name,
                type=obj.type,
                location=list(obj.location),
                rotation=list(obj.rotation_euler),
                scale=list(obj.scale),
            ))
        return SceneSnapshot(objects=objects)