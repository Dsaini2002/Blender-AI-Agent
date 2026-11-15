"""ExecutionLoop"""

import time

from dataclasses import dataclass, field
from typing import List, Optional

from .models import ModelRequest
from .models import ToolCall
from .state import ConversationState
from ..tools.base import ToolResult
from ..observability.debug import debug


@dataclass
class ExecutionRecord:
    tool_call: ToolCall
    tool_result: ToolResult


@dataclass
class AgentRunResult:
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
        state = state if state is not None else ConversationState()
        state.add_user_message(user_message)

        executed_steps: List[ExecutionRecord] = []

        # ---- DIAGNOSTIC: overall timer ----
        run_start = time.perf_counter()
        debug(f"[TIMING] === ExecutionLoop.run() start: '{user_message}' ===")

        for turn in range(1, self._max_iterations + 1):
            turn_start = time.perf_counter()

            request = self._build_request(state)
            build_elapsed = time.perf_counter() - turn_start
            debug(f"[TIMING] Turn {turn}: request built in {build_elapsed:.2f}s "
                  f"({len(request.messages)} messages, {len(request.tools)} tools)")

            llm_start = time.perf_counter()
            response = self._model_provider.generate(request)
            llm_elapsed = time.perf_counter() - llm_start

            usage = getattr(response, "usage", None)
            usage_str = ""
            if usage is not None:
                usage_str = (f" [prompt_tokens={usage.prompt_tokens}, "
                             f"completion_tokens={usage.completion_tokens}]")
            debug(f"[TIMING] Turn {turn}: LLM call took {llm_elapsed:.2f}s{usage_str}")

            if not response.has_tool_calls:
                state.add_assistant_message(response.content)
                total_elapsed = time.perf_counter() - run_start
                debug(f"[TIMING] === Done: turn {turn}, total {total_elapsed:.2f}s, "
                      f"{len(executed_steps)} tool calls ===")
                return AgentRunResult(
                    reply_text=response.content,
                    executed_steps=executed_steps,
                    turns_used=turn,
                    stopped_reason="stop",
                )

            plan = self._planner.create_plan(response)
            tools_start = time.perf_counter()
            self._execute_plan(plan, state, executed_steps)
            tools_elapsed = time.perf_counter() - tools_start
            turn_total = time.perf_counter() - turn_start
            debug(f"[TIMING] Turn {turn}: {len(plan.steps)} tool(s) executed in "
                  f"{tools_elapsed:.2f}s | turn total = {turn_total:.2f}s")

        total_elapsed = time.perf_counter() - run_start
        debug(f"[TIMING] === Stopped: max_iterations reached, total {total_elapsed:.2f}s, "
              f"{len(executed_steps)} tool calls ===")
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
        for step in plan.steps:
            step_start = time.perf_counter()
            result = self._tool_caller.call(step.tool_call)
            step_elapsed = time.perf_counter() - step_start
            debug(f"[TIMING]   tool '{step.tool_call.tool_name}' -> "
                  f"{step_elapsed:.3f}s (ok={result.success})")
            executed_steps.append(ExecutionRecord(tool_call=step.tool_call, tool_result=result))
            state.add_tool_result_message(step.tool_call, result)