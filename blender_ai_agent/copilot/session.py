"""CopilotSession"""

from typing import List, Optional

from .messages import CopilotMessage, MessageRole


class CopilotSession:

    def __init__(self):
        self._messages: List[CopilotMessage] = []
        self.current_task_id: Optional[str] = None

    def add_message(self, message: CopilotMessage) -> None:
        self._messages.append(message)

    def add_user_message(self, content: str) -> None:
        self.add_message(CopilotMessage(role=MessageRole.USER, content=content))

    def add_assistant_message(self, content: str, metadata: dict = None) -> None:
        self.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content=content, metadata=metadata or {}))

    def add_error_message(self, content: str, metadata: dict = None) -> None:
        self.add_message(CopilotMessage(role=MessageRole.ERROR, content=content, metadata=metadata or {}))

    def get_messages(self) -> List[CopilotMessage]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()
        self.current_task_id = None

    def __len__(self) -> int:
        return len(self._messages)