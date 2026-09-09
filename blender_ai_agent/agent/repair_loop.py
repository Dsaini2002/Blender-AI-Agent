"""
RepairableExecutionLoop — Step 4.8
======================================
Hinglish: Phase 3 ka ExecutionLoop sirf execute karta tha. Ye class
poora reliability cycle add karti hai:

    Execute -> Observe (Validate) -> Success?
                                        YES -> Continue
                                        NO  -> Diagnose -> Repair -> Retry
                                               (max_retries tak)
                                               Still failed -> Rollback

Composition: TransactionManager + Validator-per-tool + RecoveryManager
+ RetryPolicy + Logger — sab yahan jud rahe hain, koi bhi giant class
nahi ban rahi (SRP maintained hai, har piece apna kaam karta hai).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import uuid

from .execution_loop import AgentRunResult, ExecutionRecord
from .models import ModelRequest, ToolCall
from .state import ConversationState
from ..reliability.errors import classify_tool_error, classify_validation_error
from ..reliability.retry import RetryPolicy
from ..reliability.transaction import TransactionManager
from ..tools.base import ToolResult


@dataclass
class RepairRunResult(AgentRunResult):
    """AgentRunResult + reliability-specific info."""
    task_id: str = ""
    rolled_back: bool = False
    repairs_attempted: int = 0


class RepairableExecutionLoop:

    def __init__(
        self,
        model_provider,
        tool_caller,
        context_manager,
        planner,
        bridge,
        recovery_manager,
        logger,
        validators: Optional[Dict[str, object]] = None,
        retry_policy: Optional[RetryPolicy] = None,
        max_iterations: int = 5,
    ):
        self._model_provider = model_provider
        self._tool_caller = tool_caller
        self._context_manager = context_manager
        self._planner = planner
        self._bridge = bridge
        self._recovery_manager = recovery_manager
        self._logger = logger
        self._validators = validators or {}
        self._retry_policy = retry_policy or RetryPolicy()
        self._max_iterations = max_iterations

    def run(self, user_message: str, state: Optional[ConversationState] = None) -> RepairRunResult:
        task_id = str(uuid.uuid4())[:8]
        state = state if state is not None else ConversationState()
        state.add_user_message(user_message)

        self._logger.info("task.start", task_id=task_id, message=user_message)

        transaction = TransactionManager(self._bridge)
        transaction.begin()

        executed_steps: List[ExecutionRecord] = []
        repairs_attempted = 0

        for turn in range(1, self._max_iterations + 1):
            request = self._build_request(state)
            self._logger.info("model.request", task_id=task_id, turn=turn)
            response = self._model_provider.generate(request)

            if not response.has_tool_calls:
                self._logger.info("task.complete", task_id=task_id)
                state.add_assistant_message(response.content)
                transaction.commit()
                return RepairRunResult(
                    reply_text=response.content,
                    executed_steps=executed_steps,
                    turns_used=turn,
                    stopped_reason="stop",
                    task_id=task_id,
                    repairs_attempted=repairs_attempted,
                )

            plan = self._planner.create_plan(response)

            for step in plan.steps:
                record, repaired_count = self._execute_with_repair(step.tool_call, task_id)
                executed_steps.append(record)
                repairs_attempted += repaired_count
                state.add_tool_result_message(record.tool_call, record.tool_result)

                if not record.tool_result.success:
                    # Hinglish: Repair ke baad bhi fail — transaction rollback karo, ruk jao.
                    self._logger.error("task.failed_after_repair", task_id=task_id, tool=record.tool_call.tool_name)
                    transaction.rollback()
                    return RepairRunResult(
                        reply_text=f"Task failed: {record.tool_result.error}",
                        executed_steps=executed_steps,
                        turns_used=turn,
                        stopped_reason="rollback",
                        task_id=task_id,
                        rolled_back=True,
                        repairs_attempted=repairs_attempted,
                    )

        transaction.rollback()
        self._logger.error("task.max_iterations", task_id=task_id)
        return RepairRunResult(
            reply_text=None,
            executed_steps=executed_steps,
            turns_used=self._max_iterations,
            stopped_reason="max_iterations_reached",
            task_id=task_id,
            rolled_back=True,
            repairs_attempted=repairs_attempted,
        )

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _execute_with_repair(self, tool_call: ToolCall, task_id: str):
        """
        Hinglish: Ek tool call execute karta hai, validate karta hai,
        aur fail hone par RetryPolicy ke hisaab se repair+retry karta hai.
        Return: (final ExecutionRecord, kitni baar repair try hua)
        """
        repairs_done = 0
        current_call = tool_call

        while True:
            self._logger.info("tool.execute", task_id=task_id, tool=current_call.tool_name)
            result = self._tool_caller.call(current_call)

            if result.success:
                validated_result = self._validate(current_call, result)
                if validated_result.success:
                    self._logger.info("validation.success", task_id=task_id, tool=current_call.tool_name)
                    return ExecutionRecord(tool_call=current_call, tool_result=validated_result), repairs_done
                result = validated_result  # validation fail hui, isse aage error-handling common hai

            error = classify_tool_error(result.error)
            self._logger.error("tool.failed", task_id=task_id, tool=current_call.tool_name, code=error.code.value)

            if not error.recoverable or not self._retry_policy.should_retry(repairs_done):
                return ExecutionRecord(tool_call=current_call, tool_result=result), repairs_done

            corrected_call = self._recovery_manager.attempt_recovery(current_call, error)
            if corrected_call is None:
                return ExecutionRecord(tool_call=current_call, tool_result=result), repairs_done

            self._logger.info("repair.retry", task_id=task_id, old=current_call.arguments, new=corrected_call.arguments)
            current_call = corrected_call
            repairs_done += 1

    def _validate(self, tool_call: ToolCall, result: ToolResult) -> ToolResult:
        """Hinglish: Agar is tool ke liye validator registered hai, scene ko cross-check karo."""
        validator = self._validators.get(tool_call.tool_name)
        if validator is None:
            return result  # koi validator nahi — ToolResult.success pe hi bharosa karte hain

        validation = validator.validate(tool_call.arguments, self._bridge)
        if validation.valid:
            return result

        error = classify_validation_error(validation.reasons)
        return ToolResult.fail(error.message)

    def _build_request(self, state: ConversationState) -> ModelRequest:
        tool_definitions = self._tool_caller.get_tool_definitions()
        return ModelRequest(messages=state.get_messages(), tools=tool_definitions)