"""Agent
=====

Composition:
    Agent(model_provider, tool_caller, context_manager)
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .models import Message, ModelRequest, ToolCall
from ..tools.base import ToolResult


@dataclass
class AgentStepResult:
    reply_text: Optional[str] = None
    tool_call: Optional[ToolCall] = None
    tool_result: Optional[ToolResult] = None

    @property
    def used_tool(self) -> bool:
        return self.tool_call is not None


class Agent:

    def __init__(self, model_provider, tool_caller, context_manager):
        self._model_provider = model_provider
        self._tool_caller = tool_caller
        self._context_manager = context_manager

    def run(self, user_message: str) -> AgentStepResult:
        request = self._build_request(user_message)
        response = self._model_provider.generate(request)

        if response.has_tool_calls:
            tool_call = response.tool_calls[0]
            tool_result = self._tool_caller.call(tool_call)

            return AgentStepResult(
                reply_text=response.content,
                tool_call=tool_call,
                tool_result=tool_result,
            )

        return AgentStepResult(reply_text=response.content)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _build_request(self, user_message: str) -> ModelRequest:
        tool_definitions = self._tool_caller.get_tool_definitions()
        messages = self._build_messages(user_message)

        return ModelRequest(messages=messages, tools=tool_definitions)

    def _build_messages(self, user_message: str) -> List[Message]:
        return [Message(role="user", content=user_message)]