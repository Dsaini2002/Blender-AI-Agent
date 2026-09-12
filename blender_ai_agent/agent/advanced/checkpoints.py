"""
CheckpointManager — Step 9.33
==================================
Hinglish: Phase 4 ke SnapshotManager/RollbackManager ka reuse —
lekin complex multi-part tasks ke liye MULTIPLE named checkpoints
rakhta hai (sirf ek transaction ka begin/commit nahi).

Failure hone par, poora task restart nahi karte — sirf LATEST valid
checkpoint tak rollback karte hain, phir wahan se aage badhte hain.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ...reliability.rollback import RollbackManager
from ...reliability.snapshot import SceneSnapshot, SnapshotManager


@dataclass
class Checkpoint:
    name: str
    snapshot: SceneSnapshot


class CheckpointManager:

    def __init__(self, bridge):
        self._bridge = bridge
        self._snapshot_manager = SnapshotManager(bridge)
        self._rollback_manager = RollbackManager(bridge)
        self._checkpoints: List[Checkpoint] = []

    def create_checkpoint(self, name: str) -> Checkpoint:
        """Hinglish: Current scene state ko named checkpoint ke roop mein save karta hai."""
        snapshot = self._snapshot_manager.capture()
        checkpoint = Checkpoint(name=name, snapshot=snapshot)
        self._checkpoints.append(checkpoint)
        return checkpoint

    def latest_checkpoint(self) -> Optional[Checkpoint]:
        return self._checkpoints[-1] if self._checkpoints else None

    def rollback_to(self, name: str):
        """Hinglish: Named checkpoint tak restore karta hai. Nahi mila toh KeyError."""
        checkpoint = self._find(name)
        return self._rollback_manager.rollback_to(checkpoint.snapshot)

    def rollback_to_latest(self):
        """Hinglish: Failure hone par POORA restart nahi — sirf latest checkpoint tak wapas."""
        checkpoint = self.latest_checkpoint()
        if checkpoint is None:
            raise ValueError("No checkpoints exist to rollback to.")
        return self._rollback_manager.rollback_to(checkpoint.snapshot)

    def list_checkpoints(self) -> List[str]:
        return [c.name for c in self._checkpoints]

    def _find(self, name: str) -> Checkpoint:
        for checkpoint in self._checkpoints:
            if checkpoint.name == name:
                return checkpoint
        raise KeyError(f"No checkpoint named '{name}' found.")