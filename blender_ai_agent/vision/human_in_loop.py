"""
HumanInTheLoopGate — Step 5.17
==================================
Hinglish: Vision-driven suggestions ko seedha execute nahi karte,
khaaskar agar wo DESTRUCTIVE ho. Ye class check karti hai ki ek
proposed ToolCall ko human confirmation chahiye ya nahi — Permission
level ke hisaab se.
"""

from dataclasses import dataclass

from ..agent.models import ToolCall
from ..tools.base import Permission


@dataclass
class ConfirmationRequest:
    """Hinglish: Agent/UI ko dikhane ke liye — 'ye karne wala hoon, confirm karo'."""
    tool_call: ToolCall
    reason: str
    permission: Permission

    @property
    def requires_confirmation(self) -> bool:
        return self.permission == Permission.DESTRUCTIVE


class HumanInTheLoopGate:

    def __init__(self, tool_registry):
        self._tool_registry = tool_registry

    def check(self, tool_call: ToolCall, reason: str) -> ConfirmationRequest:
        """
        Hinglish: Vision-suggested tool call ke liye ek ConfirmationRequest
        banata hai. Caller (Agent/UI) `requires_confirmation` dekh kar
        decide karega — auto-proceed karna hai ya user se poochna hai.
        """
        tool = self._tool_registry.get(tool_call.tool_name)
        return ConfirmationRequest(
            tool_call=tool_call,
            reason=reason,
            permission=tool.permission,
        )

    def can_auto_proceed(self, tool_call: ToolCall) -> bool:
        """Hinglish: Quick check — SAFE_WRITE/READ_ONLY = haan, DESTRUCTIVE = nahi."""
        tool = self._tool_registry.get(tool_call.tool_name)
        return tool.permission != Permission.DESTRUCTIVE