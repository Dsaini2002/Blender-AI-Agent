"""
Agent — Step 3.5
===================
Hinglish: Ye Phase 3 ki MAIN class hai — sab kuch yahin jodta hai.

Agent khud LLM API nahi jaanta (ModelProvider abstraction ke peeche
hai), khud Blender nahi jaanta (Tool/ToolCaller ke peeche hai), khud
scene format nahi jaanta (ContextManager ke peeche hai). Agent sirf
in teeno ko सही order mein call karta hai — ORCHESTRATION.

Composition:
    Agent(model_provider, tool_caller, context_manager)

Ye Dependency Injection hai — Agent khud kisi provider/registry ko
create nahi karta, sab bahar se milta hai. Isse real LLM ya
MockProvider dono ke saath same Agent test/use ho sakta hai.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .models import Message, ModelRequest, ToolCall
from ..tools.base import ToolResult


@dataclass
class AgentStepResult:
    """
    Hinglish: Ek single Agent.run() call ka poora result — LLM ne
    kya bola, aur agar tool call hua toh uska result kya raha.
    """
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
        """
        Hinglish: Single-step flow:
          1. User message + available tools se ModelRequest banao
          2. LLM ko bhejo (provider.generate)
          3. Agar LLM ne tool call maanga -> execute karo
          4. Agar LLM ne seedha text bola -> wahi return karo

        Multi-step (ek response ke baad automatically agla LLM call
        karna) Step 3.7 mein Execution Loop banayega. Abhi ye sirf
        "ek turn" handle karta hai.
        """
        request = self._build_request(user_message)
        response = self._model_provider.generate(request)

        if response.has_tool_calls:
            # Hinglish: Abhi ke liye sirf PEHLA tool call handle karte
            # hain — multiple parallel tool calls Step 3.8 mein.
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
        # Hinglish: Abhi simple — sirf current user message. Conversation
        # history (purane messages yaad rakhna) Step 3.9 mein aayega.
        return [Message(role="user", content=user_message)]