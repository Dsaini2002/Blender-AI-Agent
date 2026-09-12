"""
AutonomyMode — Step 11.19
==============================
Hinglish: Kitna autonomy Agent ko diya jaaye — kitne operations
bina poochhe chal sakte hain, kitno ke liye confirmation chahiye.

DEFAULT HAMESHA CONSERVATIVE hai (spec ka explicit rule) — kabhi
AUTONOMOUS default nahi hoga, user ko explicitly opt-in karna padega.
"""

from enum import Enum

from ..tools.base import Permission


class AutonomyMode(str, Enum):
    MANUAL = "MANUAL"          # User confirms EVERYTHING
    ASSISTED = "ASSISTED"      # Safe operations auto, dangerous confirm
    AUTONOMOUS = "AUTONOMOUS"  # Safe auto + limited retries + checkpoints + stop conditions


class AutonomyPolicy:
    """
    Hinglish: Diye gaye mode ke hisaab se decide karta hai ki ek
    specific Permission level ko confirmation chahiye ya nahi.
    """

    def __init__(self, mode: AutonomyMode = AutonomyMode.ASSISTED):
        # Hinglish: Default ASSISTED hai — MANUAL se thoda usable,
        # lekin AUTONOMOUS jitna risky bilkul nahi.
        self._mode = mode

    @property
    def mode(self) -> AutonomyMode:
        return self._mode

    def requires_confirmation(self, permission: Permission) -> bool:
        if self._mode == AutonomyMode.MANUAL:
            return True  # sab kuch confirm

        if self._mode == AutonomyMode.ASSISTED:
            return permission in (Permission.DESTRUCTIVE, Permission.PYTHON_EXECUTION)

        if self._mode == AutonomyMode.AUTONOMOUS:
            # Hinglish: AUTONOMOUS mein bhi PYTHON_EXECUTION hamesha confirm hota hai —
            # kabhi bhi fully-unattended raw code execution allow nahi.
            return permission == Permission.PYTHON_EXECUTION

        return True  # unknown mode — safe default: confirm karo