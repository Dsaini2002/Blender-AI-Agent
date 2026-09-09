"""
TransactionManager — Step 4.4
=================================
Hinglish: Snapshot aur Rollback ko ek clean lifecycle mein jodta hai:

    BEGIN   -> snapshot le lo (safety net)
    COMMIT  -> sab theek raha, snapshot discard (changes rakho)
    ROLLBACK -> kuch galat hua, snapshot se scene restore karo

Ek waqt mein sirf EK active transaction ho sakta hai — nested
transactions abhi support nahi karte (zaroorat nahi hai abhi).
"""

from .rollback import RollbackManager
from .snapshot import SnapshotManager


class TransactionError(Exception):
    """Galat lifecycle usage par (jaise commit bina begin ke)."""
    pass


class TransactionManager:

    def __init__(self, bridge):
        self._bridge = bridge
        self._snapshot_manager = SnapshotManager(bridge)
        self._rollback_manager = RollbackManager(bridge)
        self._active_snapshot = None

    @property
    def is_active(self) -> bool:
        return self._active_snapshot is not None

    def begin(self) -> None:
        if self.is_active:
            raise TransactionError("A transaction is already active. Commit or rollback first.")
        self._active_snapshot = self._snapshot_manager.capture()

    def commit(self) -> None:
        if not self.is_active:
            raise TransactionError("No active transaction to commit.")
        self._active_snapshot = None  # snapshot discard — changes permanent rehte hain

    def rollback(self):
        if not self.is_active:
            raise TransactionError("No active transaction to rollback.")
        report = self._rollback_manager.rollback_to(self._active_snapshot)
        self._active_snapshot = None
        return report