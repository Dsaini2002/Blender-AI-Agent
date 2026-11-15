"""ConversationState"""

from typing import List, Optional

from .models import Message
from ..tools.base import ToolResult
from .models import ToolCall


class ConversationState:

    MAX_RECENT_MESSAGES = 30

    def __init__(self, system_prompt: Optional[str] = None):
        self._messages: List[Message] = []
        if system_prompt:
            self._messages.append(Message(role="system", content=system_prompt))

    def add_user_message(self, content: str) -> None:
        self._messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content: Optional[str]) -> None:
        self._messages.append(Message(role="assistant", content=content or ""))

    def add_tool_result_message(self, tool_call: ToolCall, tool_result: ToolResult) -> None:
        if tool_result.success:
            summary = f"Tool '{tool_call.tool_name}' succeeded: {self._compact(tool_call.tool_name, tool_result.data)}"
        else:
            summary = f"Tool '{tool_call.tool_name}' failed: {tool_result.error}"

        self._messages.append(Message(role="tool", content=summary))

    MAX_TOOL_RESULT_CHARS = 4000
    NEVER_TRUNCATE = {"library.list", "mesh.help", "asset.search_local", "vision.observe", "object.measure"}

    @classmethod
    def _compact(cls, tool_name: str, data) -> str:
        """Tool results go back to the model on every later turn: keep them short.
        scene.inspect is summarised (the live scene list is sent fresh every turn anyway)."""
        if tool_name == "scene.inspect" and isinstance(data, dict):
            objects = data.get("objects") or []
            names = ", ".join(str(o.get("name")) for o in objects[:60] if isinstance(o, dict))
            more = f" (+{len(objects) - 60} more)" if len(objects) > 60 else ""
            return f"{len(objects)} object(s): {names}{more}"
        text = str(data)
        if tool_name not in cls.NEVER_TRUNCATE and len(text) > cls.MAX_TOOL_RESULT_CHARS:
            text = text[: cls.MAX_TOOL_RESULT_CHARS] + f" … (truncated, {len(text)} chars total)"
        return text

    def get_messages(self) -> List[Message]:
        if not self._messages:
            return []

        system_messages = [m for m in self._messages if m.role == "system"]
        other_messages = [m for m in self._messages if m.role != "system"]

        trimmed = other_messages[-self.MAX_RECENT_MESSAGES:]
        return system_messages + trimmed

    def __len__(self) -> int:
        return len(self._messages)