"""AutonomyMode"""

from enum import Enum

from ..tools.base import Permission


class AutonomyMode(str, Enum):
    MANUAL = "MANUAL"          # User confirms EVERYTHING
    ASSISTED = "ASSISTED"      # Safe operations auto, dangerous confirm
    AUTONOMOUS = "AUTONOMOUS"  # Safe auto + limited retries + checkpoints + stop conditions


class AutonomyPolicy:

    def __init__(self, mode: AutonomyMode = AutonomyMode.ASSISTED):
        self._mode = mode

    @property
    def mode(self) -> AutonomyMode:
        return self._mode

    def requires_confirmation(self, permission: Permission) -> bool:
        if self._mode == AutonomyMode.MANUAL:
            return True

        if self._mode == AutonomyMode.ASSISTED:
            return permission in (Permission.DESTRUCTIVE, Permission.PYTHON_EXECUTION)

        if self._mode == AutonomyMode.AUTONOMOUS:
            return permission == Permission.PYTHON_EXECUTION

        return True