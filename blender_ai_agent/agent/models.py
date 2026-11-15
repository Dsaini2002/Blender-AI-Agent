"""LLM Request/Response Models"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    role: str  # "user", "assistant", "system", "tool"
    content: str

    def __post_init__(self):
        if self.role not in ("user", "assistant", "system", "tool"):
            raise ValueError(f"Message.role must be one of user/assistant/system/tool, got '{self.role}'")


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRequest:
    messages: List[Message]
    tools: List[ToolDefinition] = field(default_factory=list)
    temperature: float = 0.7
    model: str = "mock-model"

    def __post_init__(self):
        if not self.messages:
            raise ValueError("ModelRequest.messages must not be empty")
        if not (0.0 <= self.temperature <= 2.0):
            raise ValueError("ModelRequest.temperature must be between 0.0 and 2.0")


@dataclass
class ToolCall:
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ModelResponse:
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"  # "stop", "tool_calls", "length", etc.
    usage: Usage = field(default_factory=Usage)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0