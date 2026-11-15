"""RepairableExecutionLoop"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import json
import re
import time
import uuid

from .execution_loop import AgentRunResult, ExecutionRecord
from .models import Message, ModelRequest, ToolCall
from .prompts import SYSTEM_PROMPT
from .state import ConversationState
from .tool_selection import select_tools
from ..reliability.errors import classify_tool_error, classify_validation_error
from ..reliability.friendly_errors import friendly_error_message, is_quota_error
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

    _NEVER_DEDUPE = {"scene.inspect", "object.delete", "vision.observe"}
    MAX_RENDERS_PER_RUN = 1
    MAX_IDLE_TURNS = 2

    MAX_VISION_ITERATIONS = 3

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
        max_iterations: int = 25,
        max_failed_steps: int = 1,
        guardrails=None,
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
        # Hard safety limits (GuardrailLimits): total tool calls, repair retries, runtime, objects added/removed.
        # None = no extra limits (only max_iterations), which is what the unit tests use.
        self._guardrails = guardrails
        # Set by the controller: a no-argument callable that returns True when the user pressed Stop.
        self.should_stop = None
        # Set by the controller per request: remembered preferences / project facts, and (team mode) the
        # specialist role text plus a filter that limits which tools this role may use.
        self.memory_context = ""
        # The controller turns this off when the automatic check (post_verify) reviews renders after the run anyway:
        # asking the model to call vision.observe as well spent the same quota twice.
        self.vision_nudges = True
        self.role_hint = ""
        self.tool_filter = None
        self.ai_tools = None               # the tools the AI planner picked for this request (None = keyword rules)
        self.expects_action = False        # the request asks to build / change something: a text-only answer is sent back

    MAX_ACT_NUDGES = 2

    def run(self, user_message: str, state: Optional[ConversationState] = None) -> RepairRunResult:
        task_id = str(uuid.uuid4())[:8]
        state = state if state is not None else ConversationState(system_prompt=SYSTEM_PROMPT)
        state.add_user_message(user_message)

        self._logger.info("task.start", task_id=task_id, message=user_message)

        transaction = TransactionManager(self._bridge)
        transaction.begin()
        monitor = self._new_monitor()
        started = time.monotonic()
        start_objects = self._object_count()

        executed_steps: List[ExecutionRecord] = []
        repairs_attempted = 0
        done_keys = {}                     # call -> scene revision when it ran
        self._revision = 0                 # +1 after every successful call that changes the scene
        render_count = 0
        idle_turns = 0
        skipped_tool_calls = 0
        failed_steps = 0
        vision_checked = False
        vision_iterations = 0
        last_vision_issues = None  # None = not yet checked; [] = checked, clean; [...] = issues to fix
        vision_unavailable_reason = None
        act_nudges = 0

        for turn in range(1, self._max_iterations + 1):
            if self._stop_requested():
                return self._stopped_result(transaction, task_id, executed_steps, turn - 1, repairs_attempted)
            violation = self._check_guardrails(monitor, started, start_objects)
            if violation:
                return self._guardrail_result(violation, transaction, task_id, executed_steps, turn - 1, repairs_attempted)
            request = self._build_request(state, executed_steps)
            self._logger.info("model.request", task_id=task_id, turn=turn)
            response = self._model_provider.generate(request)

            if response.has_tool_calls:
                planned = [tc.tool_name for tc in response.tool_calls]
                self._logger.info("model.plan", task_id=task_id, turn=turn, planned_tools=planned)

            if not response.has_tool_calls:
                needs_vision_attention = (
                    self.vision_nudges
                    and render_count > 0
                    and len(executed_steps) > 4
                    and self._tool_caller.has_tool("vision.observe")
                    and vision_iterations < self.MAX_VISION_ITERATIONS
                    and (last_vision_issues is None or len(last_vision_issues) > 0)
                )
                if needs_vision_attention:
                    self._logger.info(
                        "task.vision_nudge", task_id=task_id,
                        vision_iterations=vision_iterations, issues=last_vision_issues,
                    )
                    state.add_assistant_message(response.content)
                    if last_vision_issues is None:
                        nudge_text = (
                            "Before finishing: you have not called vision.observe yet to "
                            "actually check your render. Call vision.observe now, fix any "
                            "issues it reports, then give your final reply."
                        )
                    else:
                        nudge_text = (
                            "vision.observe reported these issues on your last check: "
                            f"{last_vision_issues}. Fix these SPECIFIC issues (don't rebuild "
                            "everything), then call vision.observe again to confirm before "
                            "your final reply."
                        )
                    state.add_user_message(nudge_text)
                    continue

                # A fix round or a team step that ends without doing anything is the model giving up early
                # ("I've completed it"): send it back to work, twice at most.
                must_act = user_message.startswith("AUTOMATIC CHECK") or bool(self.role_hint) or self.expects_action
                done_any = any(getattr(getattr(r, "tool_result", None), "success", False) for r in executed_steps)
                if must_act and not done_any and act_nudges < self.MAX_ACT_NUDGES:
                    act_nudges += 1
                    self._logger.info("task.act_nudge", task_id=task_id, nudge=act_nudges)
                    try:
                        from ..observability import token_meter
                        token_meter.mark_waste("the AI answered with text only - no tool call")
                    except Exception:  # noqa: BLE001
                        pass
                    state.add_assistant_message(response.content or "(no tool call)")
                    state.add_user_message(
                        "You have not called any tool yet, so nothing in the scene changed. Reply with tool calls "
                        "now: start with the first item of the list (missing elements first - build them with the "
                        "specialised tools: mesh.building, library.place, mesh.field_markings, curve.create ...), "
                        "then the next ones. Do not answer with text only.")
                    continue

                self._logger.info("task.complete", task_id=task_id)
                state.add_assistant_message(response.content)
                transaction.commit()
                return RepairRunResult(
                    reply_text=self._with_quota_note(response.content, vision_unavailable_reason),
                    executed_steps=executed_steps,
                    turns_used=turn,
                    stopped_reason="stop",
                    task_id=task_id,
                    repairs_attempted=repairs_attempted,
                )

            plan = self._planner.create_plan(response)
            new_work_this_turn = 0
            # The same mistake repeated across one batch (e.g. 6x library.place with a model
            # name that does not exist) counts as ONE failure: the model gets to correct it
            # next turn instead of the whole step being undone.
            turn_failures = set()

            for step in plan.steps:
                if self._stop_requested():
                    return self._stopped_result(transaction, task_id, executed_steps, turn, repairs_attempted)
                if vision_unavailable_reason and step.tool_call.tool_name == "vision.observe":
                    skipped_tool_calls += 1
                    state.add_tool_result_message(
                        step.tool_call,
                        ToolResult.ok({"skipped": True, "note": "vision.observe skipped: API quota exhausted."}),
                    )
                    continue

                skip_note = self._skip_reason(step.tool_call, done_keys, render_count)
                if skip_note is not None:
                    skipped_tool_calls += 1
                    state.add_tool_result_message(
                        step.tool_call, ToolResult.ok({"skipped": True, "note": skip_note})
                    )
                    self._logger.info("tool.skipped", task_id=task_id, tool=step.tool_call.tool_name)
                    continue

                record, repaired_count = self._execute_with_repair(step.tool_call, task_id)
                new_work_this_turn += 1
                if monitor is not None:
                    monitor.record_step()
                    for _ in range(repaired_count):
                        monitor.record_retry()
                if record.tool_result.success:
                    if not self._reads_scene(record.tool_call.tool_name):
                        self._revision += 1
                    done_keys[self._call_key(record.tool_call)] = self._revision
                    if record.tool_call.tool_name == "render.preview":
                        render_count += 1
                    if record.tool_call.tool_name == "vision.observe":
                        vision_checked = True
                        vision_iterations += 1
                        last_vision_issues = (
                            list(record.tool_result.data.get("issues", []))
                            if record.tool_result.data else []
                        )
                executed_steps.append(record)
                repairs_attempted += repaired_count
                state_result = record.tool_result
                vision_quota_hit = (
                    not record.tool_result.success
                    and record.tool_call.tool_name == "vision.observe"
                    and is_quota_error(record.tool_result.error)
                )
                if vision_quota_hit:
                    vision_unavailable_reason = record.tool_result.error
                    vision_iterations = self.MAX_VISION_ITERATIONS
                    new_work_this_turn -= 1
                    self._logger.error("task.vision_quota_exhausted", task_id=task_id)
                    state.add_tool_result_message(record.tool_call, ToolResult.fail(
                        "vision.observe is unavailable right now (API quota exhausted). Do NOT call it again. "
                        "Skip visual verification and finish with a short text summary of what you built."
                    ))
                    continue
                if not state_result.success:
                    state_result = ToolResult.fail(f"{state_result.error}{self._existing_objects_hint()}")
                state.add_tool_result_message(record.tool_call, state_result)

                if not record.tool_result.success and not str(record.tool_result.error or "").startswith("Not run:"):
                    signature = (record.tool_call.tool_name, self._error_signature(record.tool_result.error))
                    if signature in turn_failures:
                        self._logger.error("task.step_failed_repeat", task_id=task_id, tool=record.tool_call.tool_name)
                        continue
                    turn_failures.add(signature)
                    failed_steps += 1
                    if failed_steps < self._max_failed_steps:
                        self._logger.error("task.step_failed_continuing", task_id=task_id, tool=record.tool_call.tool_name)
                        continue
                    self._logger.error("task.failed_after_repair", task_id=task_id, tool=record.tool_call.tool_name)
                    transaction.rollback()
                    return RepairRunResult(
                        reply_text=friendly_error_message(record.tool_result.error, tool_name=record.tool_call.tool_name)
                        if is_quota_error(record.tool_result.error)
                        else f"Task failed: {friendly_error_message(record.tool_result.error)}",
                        executed_steps=executed_steps,
                        turns_used=turn,
                        stopped_reason="rollback",
                        task_id=task_id,
                        rolled_back=True,
                        repairs_attempted=repairs_attempted,
                    )

            if new_work_this_turn == 0:
                try:
                    from ..observability import token_meter
                    token_meter.mark_waste("a step where the AI only repeated calls that were already done")
                except Exception:  # noqa: BLE001
                    pass
                idle_turns += 1
                if idle_turns >= self.MAX_IDLE_TURNS:
                    transaction.commit()
                    self._logger.info("task.no_progress_stop", task_id=task_id)
                    return RepairRunResult(
                        reply_text=self._with_quota_note((
                            f"Done. {len(executed_steps)} tool call(s) completed in {turn} turn(s). "
                            "The model kept repeating steps that were already finished, "
                            "so I stopped early - your scene has NOT been undone."
                        ), vision_unavailable_reason),
                        executed_steps=executed_steps,
                        turns_used=turn,
                        stopped_reason="no_progress",
                        task_id=task_id,
                        repairs_attempted=repairs_attempted,
                    )
            else:
                idle_turns = 0

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
            reply_text=self._with_quota_note(summary, vision_unavailable_reason),
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
    @staticmethod
    def _error_signature(error) -> str:
        """Error text with quoted names and numbers removed, so 'No model named X' == 'No model named Y'."""
        import re
        text = str(error or "")
        text = re.sub(r"'[^']*'|\"[^\"]*\"", "'?'", text)
        text = re.sub(r"-?\d+(\.\d+)?", "#", text)
        return text[:160]

    def _new_monitor(self):
        if self._guardrails is None:
            return None
        from ..autonomy.guardrails import GuardrailMonitor
        return GuardrailMonitor(self._guardrails)

    def _object_count(self) -> int:
        try:
            return len(self._bridge.get_objects())
        except Exception:  # noqa: BLE001
            return 0

    def _check_guardrails(self, monitor, started: float, start_objects: int):
        if monitor is None:
            return None
        monitor.scene_changes = abs(self._object_count() - start_objects)
        return monitor.check(elapsed_seconds=time.monotonic() - started)

    _GUARDRAIL_TEXT = {
        "MAX_STEPS_EXCEEDED": "it used the maximum number of tool calls for one request",
        "MAX_RETRIES_EXCEEDED": "too many repair retries were needed",
        "MAX_RUNTIME_EXCEEDED": "it ran longer than the time limit",
        "MAX_SCENE_CHANGES_EXCEEDED": "it added or removed more objects than the safety limit allows",
    }

    def _guardrail_result(self, violation, transaction, task_id, executed_steps, turns, repairs_attempted):
        """A safety limit was hit: keep what was built (commit), stop, and say why."""
        transaction.commit()
        self._logger.error("task.guardrail", task_id=task_id, violation=violation.value)
        reason = self._GUARDRAIL_TEXT.get(violation.value, violation.value)
        done = sum(1 for record in executed_steps if record.tool_result.success)
        return RepairRunResult(
            reply_text=(f"Stopped by a safety limit: {reason}. {done} step(s) were completed and kept. "
                        "Send 'continue' to carry on."),
            executed_steps=executed_steps,
            turns_used=turns,
            stopped_reason="guardrail",
            task_id=task_id,
            repairs_attempted=repairs_attempted,
        )

    def _stop_requested(self) -> bool:
        check = self.should_stop
        try:
            return bool(check()) if check is not None else False
        except Exception:  # noqa: BLE001
            return False

    def _stopped_result(self, transaction, task_id, executed_steps, turns, repairs_attempted):
        """User pressed Stop: keep what was built so far (commit) and end the run right away."""
        transaction.commit()
        self._logger.info("task.stopped", task_id=task_id)
        done = sum(1 for record in executed_steps if record.tool_result.success)
        return RepairRunResult(
            reply_text=f"Stopped by user after {done} completed step(s). The scene keeps what was built.",
            executed_steps=executed_steps,
            turns_used=turns,
            stopped_reason="cancelled",
            task_id=task_id,
            repairs_attempted=repairs_attempted,
        )

    @staticmethod
    def _with_quota_note(reply: Optional[str], vision_unavailable_reason: Optional[str]) -> Optional[str]:
        if not vision_unavailable_reason:
            return reply
        note = friendly_error_message(vision_unavailable_reason, tool_name="vision.observe")
        return f"{reply or 'Done.'}\n\n{note}"

    def _execute_with_repair(self, tool_call: ToolCall, task_id: str):
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
                result = validated_result

            if str(result.error or "").startswith("Not run:"):          # refused by the user: never retry
                return ExecutionRecord(tool_call=current_call, tool_result=result), repairs_done

            error = classify_tool_error(result.error)
            self._logger.error("tool.failed", task_id=task_id, tool=current_call.tool_name, code=error.code.value,
                               message=str(result.error or "")[:400], arguments=current_call.arguments)

            if not error.recoverable or not self._retry_policy.should_retry(repairs_done):
                return ExecutionRecord(tool_call=current_call, tool_result=result), repairs_done

            corrected_call = self._recovery_manager.attempt_recovery(current_call, error)
            if corrected_call is None:
                return ExecutionRecord(tool_call=current_call, tool_result=result), repairs_done

            self._logger.info("repair.retry", task_id=task_id, old=current_call.arguments, new=corrected_call.arguments)
            current_call = corrected_call
            repairs_done += 1

    def _validate(self, tool_call: ToolCall, result: ToolResult) -> ToolResult:
        validator = self._validators.get(tool_call.tool_name)
        if validator is None:
            return result

        validation = validator.validate(tool_call.arguments, self._bridge)
        if validation.valid:
            return result

        error = classify_validation_error(validation.reasons)
        return ToolResult.fail(error.message)

    def validate_visually(self, filepath: str, expected: dict, vision_context_manager, visual_validator):
        context = vision_context_manager.build_context(filepath=filepath)
        return visual_validator.validate(context.visual_observation, expected)

    def _build_request(self, state: ConversationState, executed_steps=None) -> ModelRequest:
        messages = state.get_messages()
        recent_user_text = " ".join(m.content for m in messages if m.role == "user")[-4000:]
        used = {record.tool_call.tool_name for record in (executed_steps or [])}
        all_definitions = self._tool_caller.get_tool_definitions()
        if self.ai_tools:
            # the planner read the request and picked the tools: send only those (+ core + already used) - every
            # step's request gets much smaller
            keep = set(self.ai_tools) | used
            tool_definitions = [d for d in all_definitions if d.name in keep]
        else:
            tool_definitions = select_tools(all_definitions, recent_user_text, used)
        if not self.vision_nudges:                 # the automatic check reviews the renders: no second vision call
            tool_definitions = [d for d in tool_definitions if d.name != "vision.observe"]
        if self.tool_filter is not None:
            allowed = [d for d in tool_definitions if self.tool_filter(d.name)]
            tool_definitions = allowed or tool_definitions

        extra = []
        if self.role_hint:
            extra.append(Message(role="system", content=self.role_hint))
        if self.memory_context:
            extra.append(Message(role="system", content=self.memory_context))
        if self._context_manager is not None:
            context_text = self._context_manager.build_context_text()
            if context_text:
                extra.append(Message(role="system", content=context_text))

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
        except Exception:  # noqa: BLE001 
            return ""
        if not names:
            return " (The scene currently has no objects.)"
        return " Objects that actually exist right now: " + ", ".join(names[:40]) + "."

    _OUTPUT = re.compile(r"(^scene\.save$|^render\.|export|measure|inspect|^library\.list|^asset\.search|"
                         r"^vision\.|^scene\.stats|^scene\.info)")

    @classmethod
    def _reads_scene(cls, name: str) -> bool:
        """Calls whose RESULT depends on the scene as it is now (saving the file, rendering, measuring): repeating one
        after the scene changed is new work."""
        return bool(cls._OUTPUT.search(name or ""))

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
        key = self._call_key(tool_call)
        if name not in self._NEVER_DEDUPE and key in done_keys:
            if self._reads_scene(name) and done_keys[key] != getattr(self, "_revision", 0):
                return None        # save / render / measure AFTER the scene changed: a new result, not a repeat
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