"""
ConfirmationManager — Step 6.9
==================================
Hinglish: Destructive actions ke liye "Allow/Cancel" flow. Vision ke
HumanInTheLoopGate (Phase 5) jaisa hi concept hai, lekin ye Copilot
UI ke general confirmation flow ke liye hai — kisi bhi source se
aane wale (Agent-proposed, vision-proposed) confirmable action ke liye.
"""

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

from ..agent.models import ToolCall
from ..tools.base import Permission


class ConfirmationStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class PendingConfirmation:
    action_id: str
    tool_call: ToolCall
    permission: Permission
    reason: str
    status: ConfirmationStatus = ConfirmationStatus.PENDING


class ConfirmationManager:

    def __init__(self, tool_registry):
        self._tool_registry = tool_registry
        self._pending: Dict[str, PendingConfirmation] = {}

    def request_confirmation(self, tool_call: ToolCall, reason: str = "") -> PendingConfirmation:
        """Hinglish: Ek naya confirmation request banata hai, tracking ke liye store karta hai."""
        tool = self._tool_registry.get(tool_call.tool_name)
        action_id = str(uuid.uuid4())[:8]

        confirmation = PendingConfirmation(
            action_id=action_id,
            tool_call=tool_call,
            permission=tool.permission,
            reason=reason,
        )
        self._pending[action_id] = confirmation
        return confirmation

    def approve(self, action_id: str) -> PendingConfirmation:
        confirmation = self._get_pending_or_raise(action_id)
        confirmation.status = ConfirmationStatus.APPROVED
        return confirmation

    def reject(self, action_id: str) -> PendingConfirmation:
        confirmation = self._get_pending_or_raise(action_id)
        confirmation.status = ConfirmationStatus.REJECTED
        return confirmation

    def is_approved(self, action_id: str) -> bool:
        confirmation = self._pending.get(action_id)
        return confirmation is not None and confirmation.status == ConfirmationStatus.APPROVED

    def _get_pending_or_raise(self, action_id: str) -> PendingConfirmation:
        if action_id not in self._pending:
            raise KeyError(f"No pending confirmation with id '{action_id}'.")
        return self._pending[action_id]