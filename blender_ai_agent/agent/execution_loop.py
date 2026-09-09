"""
ExecutionLoop — Step 3.7 + Step 3.8
=======================================
Hinglish: Ye Agent (Step 3.5) ka "multi-turn" upgrade hai.

Agent.run() sirf EK LLM call handle karta hai. ExecutionLoop baar-baar
LLM ko call karta hai jab tak LLM "final answer" na de:

    User Request
         ↓
    Build request (poori history + tools)
         ↓
    LLM Response
         ↓
    Tool calls hain?
      /         \
    YES          NO
     ↓            ↓
  Planner      Final Reply
     ↓          (loop ruk jaata hai)
  Execute
  har step
     ↓
  Observation
  (state mein add)
     ↓
  Loop wapas upar
  (agla LLM call)

MULTI-STEP TASKS (3.8): Ek single LLM response mein MULTIPLE tool_calls
ho sakte hain (Plan mein multiple steps) — sab sequentially execute
hote hain. Aur poora loop khud kayi TURNS le sakta hai (max_iterations
tak) — taaki "create chair" jaisa complex task multiple LLM calls mein
naturally break ho.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from .models import ModelRequest
from .models import ToolCall
from .state import ConversationState
from ..tools.base import ToolResult


@dataclass
class ExecutionRecord:
    """Ek executed step ka record — kaunsa tool chala, kya result mila."""
    tool_call: ToolCall
    tool_result: ToolResult


@dataclass
class AgentRunResult:
    """
    Hinglish: Poore multi-turn run ka final summary — Agent ke
    AgentStepResult se zyada rich hai, kyunki isme MULTIPLE steps
    ho sakte hain, alag-alag turns mein.
    """
    reply_text: Optional[str] = None
    executed_steps: List[ExecutionRecord] = field(default_factory=list)
    turns_used: int = 0
    stopped_reason: str = "stop"  # "stop" | "max_iterations_reached"

    @property
    def tool_call_count(self) -> int:
        return len(self.executed_steps)


class ExecutionLoop:

    def __init__(self, model_provider, tool_caller, context_manager, planner, max_iterations: int = 5):
        self._model_provider = model_provider
        self._tool_caller = tool_caller
        self._context_manager = context_manager
        self._planner = planner
        self._max_iterations = max_iterations

    def run(self, user_message: str, state: Optional[ConversationState] = None) -> AgentRunResult:
        """
        Hinglish: `state` optional hai — agar caller purani conversation
        continue karna chahta hai (jaise "Make it red" ke liye pichla
        context chahiye), wo apni existing ConversationState pass kar
        sakta hai. Nahi diya toh naya banta hai.
        """
        state = state if state is not None else ConversationState()
        state.add_user_message(user_message)

        executed_steps: List[ExecutionRecord] = []

        for turn in range(1, self._max_iterations + 1):
            request = self._build_request(state)
            response = self._model_provider.generate(request)

            if not response.has_tool_calls:
                # Hinglish: LLM ne final text jawab diya — loop yahin ruk jaata hai.
                state.add_assistant_message(response.content)
                return AgentRunResult(
                    reply_text=response.content,
                    executed_steps=executed_steps,
                    turns_used=turn,
                    stopped_reason="stop",
                )

            plan = self._planner.create_plan(response)
            self._execute_plan(plan, state, executed_steps)
            # Hinglish: Loop yahan RUKTA NAHI — agla turn shuru hota hai,
            # taaki LLM tool results dekh kar agla decision le sake.

        # Hinglish: max_iterations tak koi final text nahi mila —
        # safety limit hit hui (infinite loop se bachne ke liye).
        return AgentRunResult(
            reply_text=None,
            executed_steps=executed_steps,
            turns_used=self._max_iterations,
            stopped_reason="max_iterations_reached",
        )

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _build_request(self, state: ConversationState) -> ModelRequest:
        tool_definitions = self._tool_caller.get_tool_definitions()
        return ModelRequest(messages=state.get_messages(), tools=tool_definitions)

    def _execute_plan(self, plan, state: ConversationState, executed_steps: List[ExecutionRecord]) -> None:
        """Hinglish: Plan ke saare steps SEQUENTIALLY chalata hai (Step 3.8 — multi-step)."""
        for step in plan.steps:
            result = self._tool_caller.call(step.tool_call)
            executed_steps.append(ExecutionRecord(tool_call=step.tool_call, tool_result=result))
            state.add_tool_result_message(step.tool_call, result)