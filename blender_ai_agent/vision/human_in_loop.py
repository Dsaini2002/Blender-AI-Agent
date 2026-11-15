"""HumanInTheLoopGate"""

from dataclasses import dataclass

from ..agent.models import ToolCall
from ..tools.base import Permission


@dataclass
class ConfirmationRequest:
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
        tool = self._tool_registry.get(tool_call.tool_name)
        return ConfirmationRequest(
            tool_call=tool_call,
            reason=reason,
            permission=tool.permission,
        )

    def can_auto_proceed(self, tool_call: ToolCall) -> bool:
        tool = self._tool_registry.get(tool_call.tool_name)
        return tool.permission != Permission.DESTRUCTIVE