"""
SceneDiff — Step 6.20
=========================
Hinglish: Phase 4 ke SceneSnapshot ka reuse — before/after compare
karke batata hai kya CREATE hua, kya DELETE hua, aur kya MODIFY hua.

    Snapshot Before -> Tool Execution -> Snapshot After -> SceneDiff
"""

from dataclasses import dataclass, field
from typing import List

from ..reliability.snapshot import SceneSnapshot


@dataclass
class ObjectChange:
    name: str
    before_location: List[float] = None
    after_location: List[float] = None


@dataclass
class SceneDiff:
    created: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    modified: List[ObjectChange] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.created or self.deleted or self.modified)


def compute_diff(before: SceneSnapshot, after: SceneSnapshot) -> SceneDiff:
    """
    Hinglish: Do snapshots leke, ek SceneDiff banata hai. Pure
    function hai — koi state nahi rakhta, sirf compute karta hai.
    """
    before_names = set(before.object_names())
    after_names = set(after.object_names())

    diff = SceneDiff()
    diff.created = sorted(after_names - before_names)
    diff.deleted = sorted(before_names - after_names)

    for name in sorted(before_names & after_names):
        before_obj = before.get_object(name)
        after_obj = after.get_object(name)

        if before_obj.location != after_obj.location:
            diff.modified.append(ObjectChange(
                name=name,
                before_location=before_obj.location,
                after_location=after_obj.location,
            ))

    return diff