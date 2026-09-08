"""
LLM Request/Response Models — Step 3.2
==========================================
Hinglish: Real LLM APIs (OpenAI, Anthropic) jaisi shape follow karte
hain — taaki jab real provider add ho, Agent ka code badalne ki
zaroorat na pade, sirf naya provider "translate" karega apne format
mein.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    """Ek conversation message — jaise chat history ka ek turn."""
    role: str  # "user", "assistant", "system", "tool"
    content: str

    def __post_init__(self):
        if self.role not in ("user", "assistant", "system", "tool"):
            raise ValueError(f"Message.role must be one of user/assistant/system/tool, got '{self.role}'")


@dataclass
class ToolDefinition:
    """
    Hinglish: LLM ko batane ke liye ki kaunsa tool available hai aur
    uska input schema kya hai. Ye Step 3.4 (Tool Calling) mein
    ToolRegistry se automatically generate hoga.
    """
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelRequest:
    """LLM ko bheja jaane wala poora request."""
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
    """
    Hinglish: LLM ka decision — "mujhe ye tool, in arguments ke saath
    call karna hai". Ye Agent ke liye instruction hai, Tool ka result
    nahi.
    """
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Usage:
    """Token accounting — future cost-tracking ke liye foundation."""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ModelResponse:
    """
    LLM se wapas aane wala response.

    Do cases:
      1. LLM ne text jawab diya -> content set hoga, tool_calls khaali
      2. LLM ne tool call karna chaha -> tool_calls set honge, content khaali/None ho sakta hai
    """
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"  # "stop", "tool_calls", "length", etc.
    usage: Usage = field(default_factory=Usage)

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0