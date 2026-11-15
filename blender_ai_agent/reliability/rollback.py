"""RollbackManager"""

from dataclasses import dataclass, field
from typing import List

from .snapshot import SceneSnapshot, _material_name, _modifier_names


@dataclass
class RollbackReport:
    restored_transforms: List[str] = field(default_factory=list)
    deleted_new_objects: List[str] = field(default_factory=list)
    could_not_restore: List[str] = field(default_factory=list)
    removed_modifiers: List[str] = field(default_factory=list)
    restored_materials: List[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return len(self.could_not_restore) == 0


class RollbackManager:

    def __init__(self, bridge):
        self._bridge = bridge

    def rollback_to(self, snapshot: SceneSnapshot) -> RollbackReport:
        # Objects are matched by Blender's session_uid (it stays the same through a rename), by name only when there
        # is none: an original object renamed during the failed task is renamed BACK, never deleted as 'new'.
        report = RollbackReport()

        current_objects = self._bridge.get_objects()
        snapshot_names = set(snapshot.object_names())
        renamed = {}
        for obj in current_objects:
            uid = getattr(obj, "session_uid", None)
            before = snapshot.by_uid(uid) if isinstance(uid, int) else None
            if before is not None and before.name != obj.name:
                renamed[obj.name] = before.name
        for now_name, old_name in renamed.items():
            holder = next((o for o in current_objects if o.name == old_name), None)
            if holder is not None and holder.name not in renamed:
                taken = holder.name
                self._bridge.delete_object(taken)                # a NEW object took the old name
                report.deleted_new_objects.append(taken)
            self._bridge.rename_object(now_name, old_name)
            report.restored_transforms.append(f"{old_name} (renamed back from {now_name})")

        current_objects = self._bridge.get_objects()
        current_names = {obj.name for obj in current_objects}
        current_by_name = {obj.name: obj for obj in current_objects}
        known_uids = {o.uid for o in snapshot.objects if o.uid is not None}

        for obj in list(current_objects):
            name = obj.name
            if name in snapshot_names:
                continue
            uid = getattr(obj, "session_uid", None)
            if isinstance(uid, int) and uid in known_uids:
                report.could_not_restore.append(f"{name} (could not get its old name back)")
                continue                         # an original object - never delete it
            self._bridge.delete_object(name)
            report.deleted_new_objects.append(name)

        for name in snapshot_names - current_names:
            report.could_not_restore.append(name)

        for name in current_names & snapshot_names:
            snap_obj = snapshot.get_object(name)
            self._bridge.transform_object(
                name,
                location=snap_obj.location,
                rotation=snap_obj.rotation,
                scale=snap_obj.scale,
            )
            report.restored_transforms.append(name)
            self._restore_modifiers_and_material(name, snap_obj, current_by_name.get(name), report)

        return report

    def _restore_modifiers_and_material(self, name, snap_obj, current, report) -> None:
        """Undo modifiers added and material swaps made during the failed task (best effort, never raises)."""
        if current is None:
            return
        try:
            before = snap_obj.modifiers
            now = _modifier_names(current)
            if before is not None and now is not None:
                for modifier in now:
                    if modifier not in before and self._bridge.remove_modifier(name, modifier):
                        report.removed_modifiers.append(f"{name}:{modifier}")
            if snap_obj.material and _material_name(current) != snap_obj.material:
                if self._bridge.assign_material(name, snap_obj.material):
                    report.restored_materials.append(name)
        except Exception:  # noqa: BLE001
            report.could_not_restore.append(f"{name} (modifiers/material)")
