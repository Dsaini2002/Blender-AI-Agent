"""
RollbackManager — Step 4.5
==============================
Hinglish: Ek SceneSnapshot leke, current scene ko WAPAS usi state
mein le aata hai. Ye "Application-Level Rollback" hai (spec ka
Approach B) — hum khud state capture/restore karte hain.

Strategy:
  1. Snapshot ke BAAD bane naye objects -> delete karo
  2. Snapshot mein the, ab missing -> report karo (recreate abhi
     nahi karte — material/modifier state poora capture nahi hota,
     future phase mein extend hoga)
  3. Dono mein common objects -> transform (location/rotation/scale)
     wapas original values pe restore karo
"""

from dataclasses import dataclass, field
from typing import List

from .snapshot import SceneSnapshot


@dataclass
class RollbackReport:
    """Hinglish: Rollback ke baad kya-kya hua, uska record."""
    restored_transforms: List[str] = field(default_factory=list)
    deleted_new_objects: List[str] = field(default_factory=list)
    could_not_restore: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True agar sab kuch successfully restore ho gaya."""
        return len(self.could_not_restore) == 0


class RollbackManager:

    def __init__(self, bridge):
        self._bridge = bridge

    def rollback_to(self, snapshot: SceneSnapshot) -> RollbackReport:
        report = RollbackReport()

        current_objects = self._bridge.get_objects()
        current_names = {obj.name for obj in current_objects}
        snapshot_names = set(snapshot.object_names())

        # 1. Naye objects jo snapshot ke baad bane — delete karo
        for name in current_names - snapshot_names:
            self._bridge.delete_object(name)
            report.deleted_new_objects.append(name)

        # 2. Objects jo snapshot mein the but ab missing hain
        for name in snapshot_names - current_names:
            report.could_not_restore.append(name)

        # 3. Common objects — transform restore karo
        for name in current_names & snapshot_names:
            snap_obj = snapshot.get_object(name)
            self._bridge.transform_object(
                name,
                location=snap_obj.location,
                rotation=snap_obj.rotation,
                scale=snap_obj.scale,
            )
            report.restored_transforms.append(name)

        return report