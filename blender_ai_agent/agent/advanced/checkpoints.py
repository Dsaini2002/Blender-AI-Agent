"""CheckpointManager"""

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
        snapshot = self._snapshot_manager.capture()
        checkpoint = Checkpoint(name=name, snapshot=snapshot)
        self._checkpoints.append(checkpoint)
        return checkpoint

    def latest_checkpoint(self) -> Optional[Checkpoint]:
        return self._checkpoints[-1] if self._checkpoints else None

    def rollback_to(self, name: str):
        checkpoint = self._find(name)
        return self._rollback_manager.rollback_to(checkpoint.snapshot)

    def rollback_to_latest(self):
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