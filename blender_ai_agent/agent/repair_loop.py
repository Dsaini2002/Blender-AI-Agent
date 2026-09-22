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
import json
import uuid

from .execution_loop import AgentRunResult, ExecutionRecord
from .models import Message, ModelRequest, ToolCall
from .prompts import SYSTEM_PROMPT
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

    # Tools jinhe "already done" check se skip nahi karna (state-dependent hain).
    _NEVER_DEDUPE = {"scene.inspect", "object.delete"}
    # Ek request mein max kitni baar render.preview chalega (prompt ignore ho
    # jaye tab bhi code enforce karta hai).
    MAX_RENDERS_PER_RUN = 1
    # Lagatar itne turns mein koi naya kaam nahi hua -> loop rok do.
    MAX_IDLE_TURNS = 2

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
        # Hinglish: 100 bahut zyada tha — Blender ka poora UI is loop ke
        # dauraan FREEZE rehta hai (synchronous execution, koi
        # background thread nahi), isliye worst-case bahut lambi
        # (kai minute) freeze ban sakti thi. 25 zyada tar complex
        # objects (table, chair, poora furniture set) ke liye kaafi
        # hai, bina bahut lambi freeze ke risk ke.
        max_iterations: int = 25,
        # Kitne failed tool calls ke baad poora task rollback ho. 1 = purana
        # behaviour (pehli failure par rollback). Real app 3 use karta hai.
        max_failed_steps: int = 1,
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
        self._max_failed_steps = max(1, max_failed_steps)

    def run(self, user_message: str, state: Optional[ConversationState] = None) -> RepairRunResult:
        task_id = str(uuid.uuid4())[:8]
        state = state if state is not None else ConversationState(system_prompt=SYSTEM_PROMPT)
        state.add_user_message(user_message)

        self._logger.info("task.start", task_id=task_id, message=user_message)

        transaction = TransactionManager(self._bridge)
        transaction.begin()

        executed_steps: List[ExecutionRecord] = []
        repairs_attempted = 0
        done_keys = set()          # successful (tool, args) - dobara execute nahi honge
        render_count = 0
        idle_turns = 0
        skipped_tool_calls = 0
        failed_steps = 0

        for turn in range(1, self._max_iterations + 1):
            request = self._build_request(state, executed_steps)
            self._logger.info("model.request", task_id=task_id, turn=turn)
            response = self._model_provider.generate(request)

            if response.has_tool_calls:
                planned = [tc.tool_name for tc in response.tool_calls]
                self._logger.info("model.plan", task_id=task_id, turn=turn, planned_tools=planned)

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
            new_work_this_turn = 0

            for step in plan.steps:
                skip_note = self._skip_reason(step.tool_call, done_keys, render_count)
                if skip_note is not None:
                    # Hinglish: Model wahi kaam dobara maang raha hai (ya extra
                    # render). Execute mat karo - bas model ko batao.
                    skipped_tool_calls += 1
                    state.add_tool_result_message(
                        step.tool_call, ToolResult.ok({"skipped": True, "note": skip_note})
                    )
                    self._logger.info("tool.skipped", task_id=task_id, tool=step.tool_call.tool_name)
                    continue

                record, repaired_count = self._execute_with_repair(step.tool_call, task_id)
                new_work_this_turn += 1
                if record.tool_result.success:
                    done_keys.add(self._call_key(record.tool_call))
                    if record.tool_call.tool_name == "render.preview":
                        render_count += 1
                executed_steps.append(record)
                repairs_attempted += repaired_count
                state_result = record.tool_result
                if not state_result.success:
                    # Hinglish: Model ko error ke saath scene ke ASLI object
                    # naam bhi do, taaki wo stale naam (jo user ne manually
                    # delete kar diya) chhodkar khud sudhar sake.
                    state_result = ToolResult.fail(f"{state_result.error}{self._existing_objects_hint()}")
                state.add_tool_result_message(record.tool_call, state_result)

                if not record.tool_result.success:
                    failed_steps += 1
                    if failed_steps < self._max_failed_steps:
                        # Hinglish: Ek galat call (jaise purana naam) poore task ko
                        # rollback na kare - model ko error dikhao, wo agle turn
                        # mein khud correct karega.
                        self._logger.error("task.step_failed_continuing", task_id=task_id, tool=record.tool_call.tool_name)
                        continue
                    # Hinglish: Limit tak fail hua — transaction rollback karo, ruk jao.
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

            # ---- Progress check: agar poora turn sirf repeats/skips tha ----
            if new_work_this_turn == 0:
                idle_turns += 1
                if idle_turns >= self.MAX_IDLE_TURNS:
                    transaction.commit()
                    self._logger.info("task.no_progress_stop", task_id=task_id)
                    return RepairRunResult(
                        reply_text=(
                            f"Done. {len(executed_steps)} tool call(s) completed in {turn} turn(s). "
                            "The model kept repeating steps that were already finished, "
                            "so I stopped early - your scene has NOT been undone."
                        ),
                        executed_steps=executed_steps,
                        turns_used=turn,
                        stopped_reason="no_progress",
                        task_id=task_id,
                        repairs_attempted=repairs_attempted,
                    )
            else:
                idle_turns = 0

        # Hinglish: PEHLE yahan transaction.rollback() hota tha —
        # matlab agar 25 turns mein kaam poora nahi hua, ab tak ka
        # SAARA build hua kaam (jo objects/materials successfully
        # ban chuke the) delete ho jaata tha, aur user ko sirf ek
        # khaali "reply_text=None" milta tha — koi wajah nahi batayi
        # jaati thi. Ye do tarah se nuksaan-dayak tha: (1) partial
        # progress waste ho jaata tha, (2) user ko pata hi nahi
        # chalta tha kyun fail hua.
        #
        # Ab hum COMMIT karte hain (jo bhi successfully ban chuka hai,
        # wo scene mein rehta hai) aur ek clear, actionable message
        # dete hain — user ko pata chalta hai kitna kaam hua, aur wo
        # "continue" bol ke aage badha sakta hai.
        transaction.commit()
        self._logger.error("task.max_iterations", task_id=task_id)
        completed_tools = [record.tool_call.tool_name for record in executed_steps if record.tool_result.success]
        summary = (
            f"This request needed more steps than the {self._max_iterations}-step limit allows. "
            f"{len(completed_tools)} tool call(s) completed successfully "
            f"({', '.join(completed_tools[-5:])}{'...' if len(completed_tools) > 5 else ''}); "
            f"{skipped_tool_calls} repeated call(s) were skipped. "
            "The scene has NOT been undone - send 'continue' to keep going."
        )
        return RepairRunResult(
            reply_text=summary,
            executed_steps=executed_steps,
            turns_used=self._max_iterations,
            stopped_reason="max_iterations_reached",
            task_id=task_id,
            rolled_back=False,
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
            self._logger.info(
                "tool.execute",
                task_id=task_id,
                tool=current_call.tool_name,
                arguments=current_call.arguments,
            )
            result = self._tool_caller.call(current_call)

            if result.success:
                validated_result = self._validate(current_call, result)
                if validated_result.success:
                    self._logger.info(
                        "validation.success",
                        task_id=task_id,
                        tool=current_call.tool_name,
                        result=validated_result.data,
                    )
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
        """
        Hinglish: Agar is tool ke liye validator registered hai, scene
        ko cross-check karo. Ye SCENE-level validators (Phase 4) ke
        liye hai — jaise ObjectExistsValidator.

        Vision-based validation (VisualValidator, Step 5.12) alag hai
        aur explicitly `validate_visually()` se call hoti hai, kyunki
        wo image capture (expensive) maangti hai — har tool call ke
        baad automatically nahi chalani chahiye.
        """
        validator = self._validators.get(tool_call.tool_name)
        if validator is None:
            return result  # koi validator nahi — ToolResult.success pe hi bharosa karte hain

        validation = validator.validate(tool_call.arguments, self._bridge)
        if validation.valid:
            return result

        error = classify_validation_error(validation.reasons)
        return ToolResult.fail(error.message)

    def validate_visually(self, filepath: str, expected: dict, vision_context_manager, visual_validator):
        """
        Hinglish: Step 5.12 — Vision + Reliability integration.

        Agent explicitly ye call karega jab visual confirmation
        chahiye ho (jaise "make sure it's nicely framed"). Ye
        Reliability ke error-classification/repair pattern follow
        karta hai, lekin VISUAL validation ke liye.

        Return: ValidationResult (agent/caller decide karega repair
        chahiye ya nahi, jaisa normal tool validation ke saath hota hai).
        """
        context = vision_context_manager.build_context(filepath=filepath)
        return visual_validator.validate(context.visual_observation, expected)

    def _build_request(self, state: ConversationState, executed_steps=None) -> ModelRequest:
        tool_definitions = self._tool_caller.get_tool_definitions()
        messages = state.get_messages()

        # Hinglish: Scene context HAMESHA fresh banta hai (state mein
        # save nahi hota) - taaki objects move/delete hone pe LLM ko
        # stale info na mile.
        extra = []
        if self._context_manager is not None:
            context_text = self._context_manager.build_context_text()
            if context_text:
                extra.append(Message(role="system", content=context_text))

        # Hinglish: History trim hoti hai (last N messages), isliye model
        # purana kaam "bhool" jaata tha aur material.assign/create dobara
        # karta tha. Ye ledger poore run ka kaam yaad dilata hai.
        ledger = self._progress_ledger(executed_steps or [])
        if ledger:
            extra.append(Message(role="system", content=ledger))

        return ModelRequest(messages=extra + messages, tools=tool_definitions)

    def _existing_objects_hint(self) -> str:
        if self._context_manager is None:
            return ""
        try:
            summary = self._context_manager.build_context()
            names = [o["name"] for o in summary.get("objects_summary", [])]
        except Exception:  # noqa: BLE001 - hint sirf help ke liye hai, crash nahi hona chahiye
            return ""
        if not names:
            return " (The scene currently has no objects.)"
        return " Objects that actually exist right now: " + ", ".join(names[:40]) + "."

    @staticmethod
    def _call_key(tool_call: ToolCall) -> str:
        try:
            args = json.dumps(tool_call.arguments, sort_keys=True, default=str)
        except (TypeError, ValueError):
            args = repr(tool_call.arguments)
        return f"{tool_call.tool_name}|{args}"

    def _skip_reason(self, tool_call: ToolCall, done_keys, render_count: int) -> Optional[str]:
        name = tool_call.tool_name
        if name == "render.preview" and render_count >= self.MAX_RENDERS_PER_RUN:
            return ("A preview was already rendered for this request. Do NOT render again. "
                    "If everything the user asked for exists, reply with a short final text and stop.")
        if name not in self._NEVER_DEDUPE and self._call_key(tool_call) in done_keys:
            return ("This exact call was already completed successfully. Do NOT repeat it. "
                    "If all requested parts exist, reply with a short final text and stop.")
        return None

    @staticmethod
    def _progress_ledger(executed_steps) -> str:
        lines = []
        for record in executed_steps:
            if not record.tool_result.success:
                continue
            args = record.tool_call.arguments or {}
            brief = ", ".join(
                f"{k}={args[k]}" for k in ("name", "object_name", "material_name", "primitive", "type")
                if k in args
            )
            lines.append(f"- {record.tool_call.tool_name}({brief})")
        if not lines:
            return ""
        lines = lines[-60:]
        return (
            "ALREADY DONE in this request (do NOT repeat any of these; the scene already contains them):\n"
            + "\n".join(lines)
            + "\nIf the user's request is fully satisfied, reply with a short final text and no tool calls."
        )