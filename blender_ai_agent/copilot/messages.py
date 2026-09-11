"""
Message model — Step 6.5
============================
Hinglish: Copilot chat ke messages — jaisa agent/models.py mein
Message tha (LLM ke liye), ye UI-facing hai — zyada roles, aur
metadata field jisme tool naam, error code, etc. attach ho sakta hai.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"
    ERROR = "error"


@dataclass
class CopilotMessage:
    role: MessageRole
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.content and self.role != MessageRole.TOOL:
            raise ValueError("CopilotMessage.content must not be empty (except for tool messages).")