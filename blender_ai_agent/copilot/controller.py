"""CopilotController
=================

    UI -> Controller -> Agent (RepairableExecutionLoop) -> ... -> Blender
"""

import re
import os
from dataclasses import dataclass
from typing import List, Optional

from .messages import MessageRole
from .step_progress import ProgressTracker, format_duration, get_tracker
from .session import CopilotSession
from .task_splitter import split_task
from ..agent.prompts import SYSTEM_PROMPT
from ..agent.state import ConversationState


@dataclass
class SubmitResult:
    reply_text: Optional[str]
    success: bool
    task_id: str = ""
    status: str = ""          # "completed" | "partial" (stopped before the end, scene kept) | "failed"



def _token_details() -> str:
    try:
        from ..observability.token_meter import details
        return details()
    except Exception:  # noqa: BLE001
        return ""


class ProvidersFailed(RuntimeError):
    """The AI picked in the panel failed and every other one tried after it too - each with its own reason."""

    def __init__(self, failures, text: str):
        super().__init__(text)
        self.failures = list(failures)

class CopilotController:

    def __init__(self, agent, session: Optional[CopilotSession] = None, skill_registry=None,
                 tool_caller=None, tracker: Optional[ProgressTracker] = None, auto_split: bool = True,
                 split_min_parts: int = 3, split_max_parts: int = 10, verifier=None,
                 memory=None, project_id_getter=None, team_planner=None):
        self._agent = agent
        self._memory = memory
        self._project_id_getter = project_id_getter
        self._team_planner = team_planner
        self.memory_enabled = memory is not None
        self.team_enabled = team_planner is not None
        self._verifier = verifier
        if verifier is not None:
            try:                       # the review waits for the same AI's quota too (no other provider)
                verifier.quota_waiter = self._wait_for_quota
            except Exception:  # noqa: BLE001
                pass
        self._tracker = tracker if tracker is not None else get_tracker()
        self._auto_split = auto_split
        self._split_min_parts = split_min_parts
        self._split_max_parts = split_max_parts
        self.session = session if session is not None else CopilotSession()
        self._cancelled = False
        self._conversation_state = ConversationState(system_prompt=SYSTEM_PROMPT)
        self._skill_registry = skill_registry
        self._tool_caller = tool_caller

    def submit(self, user_input: str, on_progress=None) -> SubmitResult:
        """Run one request and save a run log (~/BlenderAIAgent/logs) with every tool call, error and the result."""
        import time as _time
        logger = getattr(self._agent, "_logger", None)
        start_index = len(logger.get_events()) if logger is not None and hasattr(logger, "get_events") else 0
        started = _time.time()
        result = None
        from ..observability import run_trace, token_meter
        run_trace.begin(user_input, getattr(self, "current_provider_name", "") or "",
                        getattr(self, "current_model_name", "") or "")
        token_meter.start_run()
        try:
            result = self._submit(user_input, on_progress)
            self._remember_unfinished(user_input, result)
            use = token_meter.summary()
            if use and result is not None:
                self.last_ai_use = use
                result.reply_text = ((result.reply_text or "").rstrip() + "\n\n" + use).strip()
            return result
        except BaseException as exc:
            run_trace.exception("the run", exc)
            stopped = self._cancelled or "Stopped by user" in str(exc)
            self._remember_unfinished(user_input, None, "stopped by the user" if stopped else f"failed: {str(exc)[:80]}")
            raise
        finally:
            self._write_run_log(user_input, result, logger, start_index, _time.time() - started)
            run_trace.end_file((getattr(result, "reply_text", "") or "(no result - see the error above)")
                               + (f"\nreport: {self.last_report_path}" if getattr(self, "last_report_path", "") else ""))

    def _remember_unfinished(self, user_input: str, result, why: str = "") -> None:
        """A stopped / failed / partly done run can be continued later - with any provider (panel: Continue)."""
        from . import resume
        if user_input.startswith("AUTOMATIC CHECK"):
            return
        understanding = getattr(self, "_understanding", None)
        if understanding is not None and getattr(understanding, "kind", "new") == "question":
            return
        if result is not None and result.success and not self._cancelled:
            resume.clear()
            return
        if not why:
            if self._cancelled:
                why = "stopped by the user"
            elif result is not None and getattr(result, "status", "") == "partial":
                why = "only partly done"
            else:
                why = "failed: " + ((getattr(result, "reply_text", "") or "error").strip().splitlines() or ["error"])[0][:80]
        resume.remember(user_input, understanding, why, getattr(self, "current_provider_name", ""))

    def _write_run_log(self, user_input, result, logger, start_index, seconds) -> None:
        import json
        import os
        import time as _time
        try:
            folder = os.environ.get("BLENDER_AI_LOG_DIR") or os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "logs")
            os.makedirs(folder, exist_ok=True)
            events = []
            if logger is not None and hasattr(logger, "get_events"):
                for event in logger.get_events()[start_index:]:
                    data = {k: (v if isinstance(v, (int, float, bool)) or v is None else str(v)[:600])
                            for k, v in (event.data or {}).items()}
                    events.append({"t": event.timestamp, "event": event.event, **data})
            provider = getattr(self._agent, "_model_provider", None)
            payload = {
                "request": user_input,
                "seconds": round(seconds, 1),
                "success": getattr(result, "success", None),
                "reply": getattr(result, "reply_text", None),
                "provider": getattr(self, "current_provider_name", None),
                "model": getattr(self, "current_model_name", None),
                "routing": {"fast": getattr(provider, "fast_name", None), "last_tier": getattr(getattr(provider, "last_tier", None), "value", None)},
                "events": events,
                "ai_use": _token_details(),
            }
            path = os.path.join(folder, _time.strftime("%Y%m%d_%H%M%S") + ".json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=1, ensure_ascii=False)
            from ..observability.run_trace import write_report
            self.last_report_path = write_report(path, payload)      # the readable "what happened" file
            for suffix in (".json", "_report.txt"):
                logs = sorted(f for f in os.listdir(folder) if f.endswith(suffix) and f[:8].isdigit())
                for old in logs[:-40]:                      # keep the last 40 runs
                    try:
                        os.remove(os.path.join(folder, old))
                    except OSError:
                        pass
            self.last_log_path = path
        except Exception:  # noqa: BLE001 — logging must never break a request
            pass

    def _submit(self, user_input: str, on_progress=None) -> SubmitResult:
        self._quota_waiter = None
        if self._cancelled:
            self.session.add_error_message("Task was cancelled.")
            return SubmitResult(reply_text=None, success=False)

        self.session.add_user_message(user_input)
        self._current_request = user_input
        import time as _time
        self._request_started = _time.time()
        if not user_input.startswith("AUTOMATIC CHECK"):
            self.plan_text = ""
            from . import resume
            reused = resume.take(user_input)
            if reused is not None:
                # continuing a stopped / failed run (maybe with another provider): the plan is reused - no second
                # planning request - and the agent builds only what is still missing
                self._understanding = reused
                self.plan_text = reused.plan_text() if hasattr(reused, "plan_text") else ""
                info = resume.pending() or {}
                self._log("resume", from_provider=info.get("provider", ""), why=info.get("why", ""),
                          provider=getattr(self, "current_provider_name", ""))
                self.session.add_assistant_message(
                    f"Continuing the unfinished request with {getattr(self, 'current_provider_name', 'the AI')} "
                    f"(it was {info.get('why', 'stopped')}); the plan is reused:\n{self.plan_text}")
            elif self._skill_handles(user_input):
                # a ready-made model / skill does it: no planning request (the rules write the checklist)
                from ..agent.understand import rules_understanding
                self._understanding = rules_understanding(user_input)
            else:
                self._understanding = self._understand(user_input, on_progress)
        self._learn_preferences(user_input)

        parts = self._plan(user_input)
        if len(parts) > 1:
            return self._run_steps(user_input, parts, on_progress)

        team = self._team_plan(user_input, on_progress)
        if team:
            return self._run_steps(user_input, [step.task for step in team], on_progress,
                                   roles=[step.role for step in team])

        self._tracker.begin(user_input)
        try:
            result = self._run_one(user_input, on_progress)
        except BaseException:
            self._tracker.finish(ok=False)
            raise
        self._tracker.finish(ok=result.success)
        return result

    # ---------------------------------------------------------
    # Steps + progress
    # ---------------------------------------------------------
    # A long, detailed prompt is ONE description (sizes, colours, lighting... of the same scene), not a list of
    # separate jobs: splitting it line by line gave every step only a fragment of the scene.
    SPEC_MIN_CHARS = 400
    SPEC_MIN_LINES = 8

    def _is_spec(self, user_input: str) -> bool:
        lines = [line for line in user_input.splitlines() if line.strip()]
        return len(user_input) >= self.SPEC_MIN_CHARS or len(lines) >= self.SPEC_MIN_LINES

    def _plan(self, user_input: str) -> List[str]:
        from .resume import MARK
        if not self._auto_split or self._is_spec(user_input) or user_input.startswith(MARK):
            return [user_input]           # (a continuation is one job: look at the scene, finish what is missing)
        return split_task(user_input, min_parts=self._split_min_parts, max_parts=self._split_max_parts)

    def _predict_kind(self, part: str) -> str:
        try:
            if self._skill_registry is not None and self._tool_caller is not None \
                    and self._skill_registry.find_best_match(part) is not None:
                return "skill"
        except Exception:  # noqa: BLE001 
            pass
        return "agent"

    def _progress_callback(self, on_progress):
        tracker = self._tracker

        def callback(event, data=None):
            tracker.note_event(event)
            if on_progress is not None:
                on_progress(tracker.status_line(event) or str(event), data or {})

        return callback

    def _push_status(self, on_progress, text: Optional[str] = None) -> None:
        if on_progress is not None:
            on_progress(text or self._tracker.status_line(), {})

    @staticmethod
    def _is_quota_text(text: Optional[str]) -> bool:
        try:
            from ..reliability.friendly_errors import is_quota_error
            return is_quota_error(text)
        except ImportError:  # pragma: no cover
            return "quota" in (text or "").lower()

    def _run_steps(self, user_input: str, parts: List[str], on_progress, roles: Optional[List[str]] = None) -> SubmitResult:
        tracker = self._tracker
        tracker.begin(user_input, steps=parts, kinds=["agent" if roles else self._predict_kind(p) for p in parts])
        callback = self._progress_callback(on_progress)

        plan = tracker.snapshot()
        intro = ((f"Team plan: {len(parts)} steps ({', '.join(roles)}) — " if roles else
                  f"Split this request into {len(parts)} steps — ") + "running them one by one "
                 f"(estimate ~{format_duration(plan.eta)}).")
        self.session.add_assistant_message(intro)
        self._push_status(on_progress)

        results: List[SubmitResult] = []
        stopped_reason = ""
        check_session = self._begin_verification(user_input)
        for index, part in enumerate(parts):
            if self._cancelled:
                stopped_reason = "cancelled"
                break

            tracker.start_step(index)
            self._push_status(on_progress)
            try:
                self._set_role(roles[index] if roles else "", user_input, part, index + 1, len(parts))
                # a team step is a role's job: never handed to a skill shortcut (a "sun and camera" step went to
                # build.iterate and failed)
                result = self._run_one(part, callback, verify=False, allow_skills=not roles)
            except Exception as exc:  # noqa: BLE001 
                from ..reliability.friendly_errors import friendly_error_message
                result = SubmitResult(reply_text=friendly_error_message(str(exc)), success=False)
                self.session.add_error_message(result.reply_text)

            tracker.finish_step(index, result.success, note="" if result.success else (result.reply_text or "")[:200])
            results.append(result)
            self._push_status(on_progress)

            if not result.success and self._is_quota_text(result.reply_text):
                stopped_reason = "quota"
                break

        self._set_role("", user_input, "", 0, 0)
        tracker.skip_remaining(note=stopped_reason or "skipped")
        all_ok = len(results) == len(parts) and all(r.success for r in results)
        tracker.finish(ok=all_ok)
        self._push_status(on_progress)

        summary = self._summarize(parts, results, stopped_reason)
        if check_session is not None:
            if any(r.success for r in results) and not self._cancelled and stopped_reason != "quota":
                place_text = self._arrange(user_input, check_session)
                if place_text:
                    summary += "\n" + place_text
                check_text = self._verify_and_improve(check_session, user_input, callback)
                if check_text:
                    summary += "\n" + check_text
            else:
                check_session.abort()
        if any(r.success for r in results) and not self._cancelled:
            save_text = self._final_save(user_input)
            if save_text:
                summary += "\n" + save_text
        if all_ok:
            self.session.add_assistant_message(summary)
        else:
            self.session.add_error_message(summary)
        return SubmitResult(reply_text=summary, success=all_ok)

    def _summarize(self, parts: List[str], results: List[SubmitResult], stopped_reason: str) -> str:
        snap = self._tracker.snapshot()
        done = sum(1 for r in results if r.success)
        lines = [f"Done {done}/{len(parts)} steps in {format_duration(snap.elapsed)}."]
        for index, part in enumerate(parts):
            if index < len(results):
                if results[index].success:
                    lines.append(f"✓ {index + 1}. {part}")
                else:
                    reason = (results[index].reply_text or "failed").strip().splitlines()[0][:160]
                    lines.append(f"✗ {index + 1}. {part} — {reason}")
            else:
                why = {"quota": "skipped: quota khatam", "cancelled": "skipped: cancelled"}.get(stopped_reason, "skipped")
                lines.append(f"- {index + 1}. {part} ({why})")
        return "\n".join(lines)

    def _run_one(self, user_input: str, on_progress=None, verify: bool = True, allow_skills: bool = True) -> SubmitResult:
        session = self._begin_verification(user_input) if verify else None
        try:
            result = self._run_core(user_input, on_progress, allow_skills=allow_skills)
        except BaseException:
            if session is not None:
                session.abort()
            raise
        if session is None:
            return result
        if (not result.success and result.status != "partial") or self._cancelled:
            session.abort()
            return result
        place_text = self._arrange(user_input, session)
        skill_only = getattr(self, "_skill_built", False)
        if skill_only and self._verifier is not None and not getattr(getattr(self._verifier, "cfg", None),
                                                                   "always_vision", False):
            # a ready-made model / skill result: console + measured geometry check, no picture review - no AI request
            self._verifier.vision_off = True
        try:
            check_text = self._verify_and_improve(session, user_input, on_progress)
        finally:
            if self._verifier is not None:
                self._verifier.vision_off = False
        save_text = self._final_save(user_input)
        extra = "\n\n".join(t for t in (place_text, check_text, save_text) if t)
        if extra:
            self.session.add_assistant_message(extra)
            return SubmitResult(reply_text=(result.reply_text or "") + "\n\n" + extra, success=result.success,
                                task_id=result.task_id, status=result.status)
        return result

    def _run_core(self, user_input: str, on_progress=None, allow_skills: bool = True) -> SubmitResult:
        self._skill_built = False
        skill_result = self._try_skill_fast_path(user_input) if allow_skills else None
        if skill_result is not None:
            return skill_result
        return self._run_agent(user_input, on_progress)

    def _run_agent(self, user_input: str, on_progress=None) -> SubmitResult:
        logger = getattr(self._agent, "_logger", None)
        if logger is not None:
            logger.callback = on_progress
        if hasattr(self._agent, "should_stop"):
            self._agent.should_stop = lambda: self._cancelled
        if hasattr(self._agent, "vision_nudges"):
            self._agent.vision_nudges = not self._verifier_reviews_renders()
        understanding = getattr(self, "_understanding", None)
        fixing = user_input.startswith("AUTOMATIC CHECK")
        if hasattr(self._agent, "memory_context"):
            memory = self._memory_context(user_input)
            note = understanding.builder_note() if understanding is not None and not fixing else ""
            self._agent.memory_context = "\n\n".join(t for t in (memory, note) if t)
        if hasattr(self._agent, "ai_tools"):
            known = None
            try:
                known = {d.name for d in self._tool_caller.get_tool_definitions()} if self._tool_caller else None
            except Exception:  # noqa: BLE001
                known = None
            picked = understanding.tool_set(known) if understanding is not None and understanding.source == "ai" \
                and not fixing else set()
            self._agent.ai_tools = picked or None
        if hasattr(self._agent, "expects_action"):
            self._agent.expects_action = bool(understanding is not None and understanding.source == "ai"
                                              and understanding.kind in ("new", "edit")
                                              and not fixing)
        begin_task = getattr(getattr(self._agent, "_model_provider", None), "begin_task", None)
        if callable(begin_task):
            # Route on the WHOLE request, never on one step of it (a short step of a big scene is not a simple job).
            whole = getattr(self, "_current_request", "") or user_input
            begin_task(user_input if user_input.startswith("AUTOMATIC CHECK") else whole)

        self._last_tool_calls = None
        try:
            # Only the AI picked in the panel is used. Quota / rate limit used up: wait until it has tokens again
            # (countdown in the panel, Stop cancels) and go on from where it stopped - the scene is kept.
            text = user_input
            while True:
                try:
                    run_result = self._agent.run(text, state=self._conversation_state)
                    break
                except Exception as exc:  # noqa: BLE001
                    if self._cancelled or not self._wait_for_quota(str(exc)):
                        raise
                    text = (user_input + "\n\n(The previous attempt stopped because the AI quota ran out. What was "
                            "built before is still in the scene - check it and continue; do not build it again.)")
            steps = getattr(run_result, "executed_steps", None)
            if isinstance(steps, (list, tuple)):
                self._last_tool_calls = sum(1 for r in steps if getattr(getattr(r, "tool_result", None), "success", False))
        except Exception as exc:  # noqa: BLE001
            from ..reliability.friendly_errors import (friendly_error_message, is_quota_error,
                                                      providers_failed_message)
            if isinstance(exc, ProvidersFailed):
                friendly = providers_failed_message(exc.failures)
                self.session.add_error_message(friendly)
                return SubmitResult(reply_text=friendly, success=False)
            if not is_quota_error(str(exc)):
                raise
            friendly = friendly_error_message(str(exc))
            self.session.add_error_message(friendly)
            return SubmitResult(reply_text=friendly, success=False)
        finally:
            if logger is not None:
                logger.callback = None

        task_id = getattr(run_result, "task_id", "")
        rolled_back = getattr(run_result, "rolled_back", False)
        if getattr(run_result, "stopped_reason", "") in ("cancelled", "guardrail"):
            stopped = run_result.reply_text or "Stopped by user."
            self.session.add_error_message(stopped, metadata={"task_id": task_id})
            return SubmitResult(reply_text=stopped, success=False, task_id=task_id)

        if rolled_back or run_result.reply_text is None:
            error_text = run_result.reply_text or "Task could not be completed."
            self.session.add_error_message(error_text, metadata={"task_id": task_id})
            return SubmitResult(reply_text=error_text, success=False, task_id=task_id)

        steps = getattr(run_result, "executed_steps", []) or []
        status = self._run_status(user_input, run_result, steps)
        if status == "failed":
            text = ("Nothing was built or changed: the AI answered without using any tool. "
                    f"Its answer: {(run_result.reply_text or '').strip()[:300]}")
            self.session.add_error_message(text, metadata={"task_id": task_id})
            return SubmitResult(reply_text=text, success=False, task_id=task_id, status="failed")
        if status == "partial":
            text = "PARTLY DONE - " + (run_result.reply_text or "")
            self.session.add_error_message(text, metadata={"task_id": task_id})
            self._remember_task(user_input, text, self._objects_from_steps(steps))
            return SubmitResult(reply_text=text, success=False, task_id=task_id, status="partial")
        self.session.add_assistant_message(run_result.reply_text, metadata={"task_id": task_id})
        self._remember_task(user_input, run_result.reply_text, self._objects_from_steps(steps))
        return SubmitResult(reply_text=run_result.reply_text, success=True, task_id=task_id, status="completed")

    _QUESTION = re.compile(r"(\?\s*$)|^\s*(what|which|how|why|where|who|is|are|does|do|can|kya|kaun|kaise|kyun|kitne|"
                           r"kitna|kahan|batao|bata|explain|describe|list|show me the|tell me)\b", re.IGNORECASE)

    def _run_status(self, user_input: str, run_result, steps) -> str:
        """Did the run really do the job? 'completed', 'partial' (hit the step limit) or 'failed' (asked to build or
        change something, but not one tool that changes the scene succeeded)."""
        if getattr(run_result, "stopped_reason", "") == "max_iterations_reached":
            return "partial"
        if not isinstance(getattr(run_result, "executed_steps", None), (list, tuple)):
            return "completed"          # (a result without its step list - nothing to judge it by)
        understanding = getattr(self, "_understanding", None)
        if understanding is not None and understanding.kind == "question":
            return "completed"
        from ..agent.repair_loop import RepairableExecutionLoop
        changed = [r for r in steps if getattr(getattr(r, "tool_result", None), "success", False)
                   and not RepairableExecutionLoop._reads_scene(getattr(r.tool_call, "tool_name", ""))]
        if not changed and not user_input.startswith("AUTOMATIC CHECK") and not self._QUESTION.search(user_input.strip()):
            return "failed"
        return "completed"

    # ---------------------------------------------------------
    # Automatic check + improve
    # ---------------------------------------------------------
    def _verifier_reviews_renders(self) -> bool:
        try:
            return self._verifier is not None and self._verifier.cfg.mode == "full"
        except Exception:  # noqa: BLE001
            return False

    def _begin_verification(self, user_input: str):
        verifier = self._verifier
        if verifier is None:
            return None
        try:
            return verifier.begin(user_input)
        except Exception:  # noqa: BLE001 
            return None

    def _verify_and_improve(self, session, user_input: str, on_progress=None) -> str:
        verifier = self._verifier
        understanding = getattr(self, "_understanding", None)
        try:          # the deep check verifies every checklist line (counts, places) from every angle
            verifier.checklist = list(understanding.checklist) if understanding is not None \
                and understanding.kind == "new" else []
        except Exception:  # noqa: BLE001
            pass
        history = []
        fix_failure = ""
        stop_reason = ""
        def show(text: str) -> None:
            try:
                from . import activity
                activity.set_check(text)
            except Exception:  # noqa: BLE001
                pass
            self._log("check.progress", text=text)        # in the .json log + report (and the live trace)
            if on_progress is not None:
                try:
                    on_progress(text, {})
                except Exception:  # noqa: BLE001
                    pass

        def summary(r) -> str:
            bits = []
            if r.score is not None:
                bits.append(f"vision {r.score:g}/10")
            elif r.vision_note:
                bits.append("vision skipped")
            count = len(r.actionable) + sum(1 for p in r.geometry if p.get("severity") == "high") + len(r.missing or []) \
                + len(r.problems)
            bits.append(f"{count} problem(s)" if count else "no problems")
            return ", ".join(bits)

        show("Auto-check: rendering and reviewing the result")
        from ..observability import token_meter
        try:
            token_meter.set_phase("check")
            report = verifier.assess(user_input, session.end(), 0)
            history.append(report)
            self._log_review(report)
            show(f"Auto-check: {summary(report)}")
            rounds = 0
            cfg = verifier.cfg
            limit = cfg.max_rounds if not getattr(cfg, "until_fixed", False) else max(cfg.max_rounds, 1)
            stall_limit = getattr(cfg, "stall_rounds", 2)
            best = verifier.badness(report) if hasattr(verifier, "badness") else None
            stalled = 0
            idle_rounds = 0
            while report.needs_fix and rounds < limit and not self._cancelled:
                rounds += 1
                self.session.add_assistant_message(verifier.announce(report, rounds))
                show(f"Auto-check round {rounds}: fixing {summary(report)}")
                fix_session = verifier.begin(user_input, baseline=session.baseline)
                prompt = verifier.fix_prompt(user_input, report, rounds)
                if idle_rounds:
                    prompt += ("\nIMPORTANT: in the last round you changed NOTHING. Do not explain or apologise - call the "
                               "tools now and fix the first problem in the list, then the next ones.")
                self._save_fix_prompt(report, prompt, rounds)
                token_meter.set_phase(f"fix {rounds}")
                try:
                    fix_result = self._run_fix(prompt, report, idle_rounds, on_progress)
                except BaseException:
                    if fix_session is not None:
                        fix_session.abort()
                    raise
                if fix_session is None:
                    break
                if not fix_result.success:
                    fix_session.abort()
                    fix_failure = (fix_result.reply_text or "fix could not run").strip().splitlines()[0][:120]
                    break
                show(f"Auto-check round {rounds}: checking the fix")
                token_meter.set_phase("check")
                new_report = verifier.assess(user_input, fix_session.end(), rounds)
                history.append(new_report)
                self._log_review(new_report)
                show(f"Auto-check round {rounds}: {summary(new_report)}")
                if not getattr(cfg, "until_fixed", False):
                    worse = new_report.score is not None and report.score is not None and new_report.score < report.score - 0.5
                    report = new_report
                    if worse:
                        break
                    continue
                report = new_report
                did_nothing = getattr(self, "_last_tool_calls", None) == 0
                idle_rounds = idle_rounds + 1 if did_nothing else 0
                if hasattr(verifier, "quota_gone") and verifier.quota_gone(report) and not report.actionable:
                    stop_reason = "the Gemini quota is used up, so the result cannot be checked again"
                    break
                current = verifier.badness(report)
                if did_nothing or not (best is None or current < best):
                    token_meter.mark_waste(f"fix round {rounds} brought no improvement",
                                           token_meter.phase_tokens(f"fix {rounds}"))
                if did_nothing:
                    stalled += 1          # nothing changed: a different score is only reviewer noise
                    if stalled >= stall_limit:
                        stop_reason = f"the agent made no changes in {stalled} rounds"
                        break
                elif best is None or current < best:
                    best, stalled = current, 0
                else:
                    stalled += 1
                    if stalled >= stall_limit:
                        stop_reason = f"no improvement in the last {stalled} rounds"
                        break
        except Exception as exc:  # noqa: BLE001
            session.abort()
            if not history:
                return f"Auto-check could not run ({type(exc).__name__}: {str(exc)[:120]}); the result is unchanged."
            return verifier.format_history(history) + f"\n  (further auto-fix stopped: {type(exc).__name__}: {str(exc)[:100]})"
        text = verifier.format_history(history)
        if history and history[-1].needs_fix:
            if self._cancelled:
                stop_reason = "stopped by user"
            elif not stop_reason and not fix_failure and len(history) - 1 >= getattr(verifier.cfg, "max_rounds", 0) \
                    and getattr(verifier.cfg, "until_fixed", False):
                stop_reason = f"safety limit of {verifier.cfg.max_rounds} rounds reached"
        if stop_reason:
            text += f"\n  (auto-fix stopped: {stop_reason})"
        return text + (f"\n  (auto-fix could not run: {fix_failure})" if fix_failure else "")

    def _log_review(self, report) -> None:
        """The whole review of one check round in the run log (and so in the report and the live trace)."""
        try:
            self._log("check.review", round=report.round, folder=getattr(report, "folder", ""),
                      score=report.score, vision_note=report.vision_note, missing=list(report.missing or []),
                      problems=[f"[{p.get('severity', '?')}] {p.get('where', '')}: {p.get('issue', '')} -> fix: "
                                f"{p.get('fix', '')}" for p in report.problems],
                      geometry=[f"[{p.get('severity', '?')}] {p.get('where', '')}: {p.get('issue', '')} -> fix: "
                                f"{p.get('fix', '')}" for p in report.geometry],
                      console=len(report.actionable), needs_fix=report.needs_fix)
        except Exception:  # noqa: BLE001
            pass

    def _save_fix_prompt(self, report, prompt: str, round_no: int) -> None:
        """What the agent is told to fix: fix_prompt.txt next to that round's images and review.txt."""
        folder = getattr(report, "folder", "")
        path = ""
        if folder:
            try:
                os.makedirs(folder, exist_ok=True)
                path = os.path.join(folder, "fix_prompt.txt")
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(prompt)
            except OSError:
                path = ""
        self._log("check.fix_sent", round=round_no, file=path, prompt=prompt[:1500])

    # A result that is far off (low score, several elements missing) or a fix round that did nothing is re-planned
    # by the team lead into steps, instead of asking one agent turn to fix everything at once.
    TEAM_FIX_SCORE = 5.0
    TEAM_FIX_MISSING = 3

    def _run_fix(self, prompt: str, report, idle_rounds: int, on_progress=None) -> SubmitResult:
        missing = len(getattr(report, "missing", None) or [])
        score = getattr(report, "score", None)
        big = (score is not None and score <= self.TEAM_FIX_SCORE) or missing >= self.TEAM_FIX_MISSING or idle_rounds > 0
        if not big or self._team_planner is None or not self.team_enabled:
            return self._run_agent(prompt, on_progress)
        try:
            steps = self._team_planner.plan(prompt)
        except Exception as exc:  # noqa: BLE001
            from ..reliability.friendly_errors import is_quota_error
            if is_quota_error(str(exc)):
                if not self._wait_for_quota(str(exc)):
                    raise
                steps = self._team_planner.plan(prompt)
            else:
                steps = []
        self._log("team.fix_plan", steps=[f"{s.role}: {s.task[:160]}" for s in steps], missing=missing, score=score)
        if len(steps) < 2:
            return self._run_agent(prompt, on_progress)
        goal = getattr(self, "_current_request", "") or prompt
        total_calls, ok_any, last = 0, False, None
        for index, step in enumerate(steps):
            if self._cancelled:
                break
            self._set_role(step.role, goal, step.task, index + 1, len(steps))
            try:
                last = self._run_agent(f"AUTOMATIC CHECK fix step {index + 1}/{len(steps)}: {step.task}\n\n{prompt}",
                                       on_progress)
            finally:
                self._set_role("", goal, "", 0, 0)
            total_calls += getattr(self, "_last_tool_calls", 0) or 0
            ok_any = ok_any or bool(last and last.success)
            if last is not None and not last.success and self._is_quota_text(last.reply_text):
                break
        self._last_tool_calls = total_calls
        if last is None:
            return SubmitResult(reply_text="fix could not run", success=False)
        return SubmitResult(reply_text=last.reply_text, success=ok_any or last.success, task_id=last.task_id)

    def _skill_handles(self, user_input: str) -> bool:
        """A ready skill (campfire, tent, house ...) will build this request by itself - no AI needed."""
        from .resume import MARK
        if self._skill_registry is None or self._tool_caller is None or user_input.startswith(MARK) \
                or self._is_spec(user_input):
            return False
        try:
            return self._skill_registry.find_best_match(user_input) is not None
        except Exception:  # noqa: BLE001
            return False

    def _try_skill_fast_path(self, user_input: str) -> Optional[SubmitResult]:
        if self._skill_registry is None or self._tool_caller is None:
            return None
        from .resume import MARK
        if user_input.startswith(MARK):
            return None                    # continuing: the agent finishes what is there, a skill would rebuild it

        skill = self._skill_registry.find_best_match(user_input)
        if skill is None:
            return None

        skill_result = skill.execute(self._extract_skill_context(user_input))

        if not skill_result.success:
            error_text = skill_result.error or f"'{skill.name}' skill could not finish."
            self.session.add_error_message(error_text)
            return SubmitResult(reply_text=error_text, success=False)

        data = skill_result.data if isinstance(skill_result.data, dict) else {}
        notes = data.get("notes") or []
        built = self._describe_skill_result(skill.name, data, len(skill_result.steps_completed))
        reply_text = f"Done — {built}"
        self._remember_task(user_input, reply_text, self._objects_from_data(data))
        for note in notes:
            reply_text += f"\n{note}"
        self.session.add_assistant_message(reply_text)
        rest = self._skill_leftover(user_input)
        self._skill_built = not rest            # built by trusted code alone: checked without pictures
        if rest:
            # the skill built its part; the rest of the request (save the file, colours, extra things) is the
            # agent's job - a short 'house + save' request used to lose the save
            follow = self._run_agent(f"{user_input}\n\nThe {skill.name} skill has ALREADY built: {built}. Do NOT "
                                     f"rebuild it. Do only what the request still needs: {rest}.")
            reply_text += "\n" + (follow.reply_text or "")
            return SubmitResult(reply_text=reply_text, success=follow.success or follow.status == "failed",
                                status="completed" if follow.success or follow.status == "failed" else follow.status)
        return SubmitResult(reply_text=reply_text, success=True, status="completed")

    _LEFTOVER = (
        (re.compile(r"\bsave|\.blend\b|\bfile\s+(bana|banao|me|mein)|save\s*kar", re.IGNORECASE), "save the file"),
        (re.compile(r"\brender\b|\bimage\b|\bpicture\b|\bphoto\b", re.IGNORECASE), "render it"),
        (re.compile(r"\bcollections?\b|\borgani[sz]e", re.IGNORECASE), "organise the collections"),
        (re.compile(r"\bexport\b|\.fbx\b|\.obj\b|\.glb\b", re.IGNORECASE), "export it"),
        (re.compile(r"\bcamera\b", re.IGNORECASE), "set the camera"),
    )

    def _skill_leftover(self, user_input: str) -> str:
        return ", ".join(what for pattern, what in self._LEFTOVER if pattern.search(user_input))

    def _final_save(self, user_input: str) -> str:
        """The user asked for a file: after the automatic fixes changed the scene, write it AGAIN (same name) and check
        it on disk - so the file is the final, repaired scene, never an earlier state."""
        from ..agent.tool_selection import wants_save
        from ..tools import site_tools
        last = dict(site_tools.LAST_SAVE)
        started = getattr(self, "_request_started", 0.0)
        saved_now = bool(last) and last.get("time", 0) >= started
        understanding = getattr(self, "_understanding", None)
        asked = wants_save(user_input) or bool(understanding is not None and understanding.save_wanted)
        if not (asked or saved_now) or self._tool_caller is None:
            return ""
        filename = last.get("filepath") if saved_now else (getattr(understanding, "filename", "") or "")
        if not filename:
            match = re.search(r"([\w\-. ]+\.blend)\b", user_input)
            filename = match.group(1).strip() if match else \
                "_".join(re.findall(r"[A-Za-z0-9]+", user_input)[:4]) + ".blend"
        try:
            from ..agent.models import ToolCall
            result = self._tool_caller.call(ToolCall(tool_name="scene.save", arguments={"filename": filename}))
        except Exception as exc:  # noqa: BLE001
            return f"FILE NOT SAVED: {exc}"
        if not result.success:
            return f"FILE NOT SAVED: {result.error}"
        data = result.data or {}
        size = data.get("bytes", 0)
        self._log("save.final", filepath=data.get("filepath", ""), bytes=size)
        return f"Saved the final scene: {data.get('filepath')} ({size / 1048576:.1f} MB, checked on disk)"

    # ---------------------------------------------------------
    # Team mode
    # ---------------------------------------------------------
    def _team_plan(self, user_input: str, on_progress=None):
        """Big single-sentence request -> lead plans role steps. [] = run it as one normal agent request."""
        from .resume import MARK
        if user_input.startswith("AUTOMATIC CHECK") or user_input.startswith(MARK):
            return []
        if self._team_planner is None or not self.team_enabled:
            self._log("team.skip", reason="team mode off" if self._team_planner is not None else "no team planner")
            return []
        try:
            from ..multi_agent.team import is_big_request
            if not is_big_request(user_input):
                self._log("team.skip", reason="small request")
                return []
            skill = None
            # a long, detailed spec is a scene for the team; a skill shortcut (the simple house builder) would
            # build a fraction of it - a villa spec once became a 4-wall house
            if self._skill_registry is not None and self._tool_caller is not None and not self._is_spec(user_input):
                skill = self._skill_registry.find_best_match(user_input)
            if skill is not None:
                self._log("team.skip", reason=f"skill {getattr(skill, 'name', skill)} handles it")
                return []
            if on_progress is not None:
                on_progress("Planning the team steps", {})
            from ..observability import run_trace
            run_trace.note("TEAM   asking the lead AI for a plan …")
            try:
                steps = self._team_planner.plan(user_input)
            except Exception as exc:  # noqa: BLE001
                from ..reliability.friendly_errors import is_quota_error
                if not is_quota_error(str(exc)) or not self._wait_for_quota(str(exc)):
                    raise
                steps = self._team_planner.plan(user_input)
            self._log("team.plan", source=getattr(self._team_planner, "last_source", ""),
                      steps=[f"{s.role}: {s.task[:160]}" for s in steps],
                      raw=(getattr(self._team_planner, "last_raw", "") or "")[:600])
            return steps
        except Exception as exc:  # noqa: BLE001 — planning is optional; quota errors etc. fall back to one agent run
            from ..reliability.friendly_errors import is_quota_error
            if is_quota_error(str(exc)):
                raise
            self._log("team.plan_failed", error=str(exc)[:300])
            return []

    def _log(self, event: str, **data) -> None:
        logger = getattr(self._agent, "_logger", None)
        if logger is not None and hasattr(logger, "info"):
            try:
                logger.info(event, **data)
            except Exception:  # noqa: BLE001
                pass

    def _set_role(self, role: str, goal: str, task: str, number: int, total: int) -> None:
        agent = self._agent
        if not hasattr(agent, "role_hint"):
            return
        if not role:
            agent.role_hint, agent.tool_filter = "", None
            return
        from ..multi_agent.team import role_brief, role_filter
        agent.role_hint = role_brief(role, goal, task, number, total)
        agent.tool_filter = role_filter(role)

    # ---------------------------------------------------------
    # Memory
    # ---------------------------------------------------------
    def _project_id(self) -> str:
        try:
            return (self._project_id_getter() if self._project_id_getter else "") or "unsaved"
        except Exception:  # noqa: BLE001
            return "unsaved"

    def _learn_preferences(self, user_input: str) -> None:
        if self._memory is None or not self.memory_enabled or user_input.startswith("AUTOMATIC CHECK"):
            return
        if self._is_spec(user_input):                     # a scene description is not a standing preference
            return
        try:
            for saved in self._memory.learn_from_request(user_input):
                self.session.add_assistant_message(f"Remembered: {saved}")
        except Exception:  # noqa: BLE001 — memory must never block a request
            pass

    def _memory_context(self, user_input: str) -> str:
        if self._memory is None or not self.memory_enabled:
            return ""
        try:
            return self._memory.context_for(user_input, self._project_id())
        except Exception:  # noqa: BLE001
            return ""

    def _remember_task(self, user_input: str, reply: str, objects) -> None:
        if self._memory is None or not self.memory_enabled or user_input.startswith("AUTOMATIC CHECK"):
            return
        try:
            self._memory.record_task(user_input, reply or "", objects, self._project_id())
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _objects_from_steps(steps) -> list:
        names = []
        for record in steps or []:
            result = getattr(record, "tool_result", None)
            if result is None or not result.success:
                continue
            tool = record.tool_call.tool_name
            if tool.startswith(("scene.", "render.", "vision.", "object.measure", "object.delete", "mesh.help", "library.list",
                                "asset.search", "retopology.analyze")):
                continue
            names.extend(CopilotController._objects_from_data(result.data if isinstance(result.data, dict) else {}))
            args = record.tool_call.arguments or {}
            if not result.data and isinstance(args.get("name"), str):
                names.append(args["name"])
        return list(dict.fromkeys(names))

    @staticmethod
    def _objects_from_data(data: dict) -> list:
        names = []
        for key in ("name", "new_name", "object_name"):
            if isinstance(data.get(key), str):
                names.append(data[key])
        for key in ("objects", "roots", "created"):
            value = data.get(key)
            if isinstance(value, list):
                names.extend(str(v) for v in value if isinstance(v, str))
            elif isinstance(value, dict):
                for items in value.values():
                    if isinstance(items, list):
                        names.extend(str(v) for v in items if isinstance(v, str))
        return names

    @staticmethod
    def _describe_skill_result(skill_name: str, data: dict, steps: int) -> str:
        """Short, readable summary of a skill run (no raw dicts)."""
        label = skill_name.replace("_", " ")
        name = data.get("name") or data.get("model") or data.get("root")
        objects = data.get("objects") or data.get("roots") or data.get("created") or []
        if isinstance(objects, dict):
            objects = [n for names in objects.values() if isinstance(names, list) for n in names]
        count = len(objects) if isinstance(objects, (list, tuple)) else 0
        parts = [f"built with the {label} skill"]
        if name:
            parts.append(f"'{name}'")
        if data.get("source") == "downloaded":
            parts.append("(downloaded CC0 model)")
        if count:
            parts.append(f"{count} object(s)")
        elif steps:
            parts.append(f"{steps} step(s)")
        return " ".join(parts) + "."

    @staticmethod
    def _extract_skill_context(user_input: str) -> dict:
        _COLOR_MAP = {
            "red": [0.7, 0.1, 0.1, 1.0], "blue": [0.15, 0.35, 0.75, 1.0],
            "green": [0.15, 0.55, 0.2, 1.0], "yellow": [0.9, 0.8, 0.1, 1.0],
            "white": [0.95, 0.95, 0.95, 1.0], "black": [0.05, 0.05, 0.05, 1.0],
            "brown": [0.4, 0.25, 0.12, 1.0], "pink": [0.9, 0.5, 0.6, 1.0],
            "purple": [0.4, 0.15, 0.55, 1.0], "orange": [0.85, 0.45, 0.1, 1.0],
            "grey": [0.5, 0.5, 0.5, 1.0], "gray": [0.5, 0.5, 0.5, 1.0],
        }
        text = user_input.lower()
        context: dict = {"task": user_input}

        import re
        if re.search(r"\b(delete|remove|clear|hatao|hata)\b.*\b(cube|light|default|startup)\b", text):
            context["clear_defaults"] = True
        for part_key, part_words in (
            ("wall_color", ("wall", "walls")),
            ("roof_color", ("roof",)),
            ("door_color", ("door",)),
            ("window_color", ("window", "windows")),
        ):
            for color_word, rgba in _COLOR_MAP.items():
                if color_word in text and any(w in text for w in part_words):
                    context[part_key] = rgba
                    break
        return context

    ai_understanding = True          # the AI reads the request first (False = only the built-in rules)

    def _understand(self, user_input: str, on_progress=None):
        """Before building: the AI writes down WHAT will be built (checklist with counts and positions), which tools
        are needed, what has no tool, and whether a file is wanted. Shown to the user first."""
        from ..agent.understand import rules_understanding, understand
        provider = getattr(self._agent, "_model_provider", None)
        definitions = []
        try:
            definitions = self._tool_caller.get_tool_definitions() if self._tool_caller is not None else []
        except Exception:  # noqa: BLE001
            definitions = []
        usable = self.ai_understanding and self._ai_ready() and definitions
        if not usable:
            result = rules_understanding(user_input)
        else:
            if on_progress is not None:
                try:
                    on_progress("Reading the request - writing the checklist first", {})
                except Exception:  # noqa: BLE001
                    pass

            from ..observability import token_meter
            token_meter.set_phase("plan")
            try:
                result = understand(self._ask_ai, user_input, definitions)
            except Exception as exc:  # noqa: BLE001
                from ..reliability.friendly_errors import is_quota_error
                if is_quota_error(str(exc)) and self._cancelled:
                    raise
                result = rules_understanding(user_input)
                result.note = f"the AI could not read the request ({str(exc)[:120]}) - used the built-in rules"
        from ..observability import token_meter
        token_meter.set_phase("build")
        self._log("plan.understood", source=result.source, kind=result.kind,
                  checklist=[i.label() for i in result.checklist], tools=result.tools[:40], missing=result.missing,
                  save=result.save_wanted, filename=result.filename, note=result.note)
        plan = result.plan_text()
        self.plan_text = plan if result.kind != "question" else ""
        if plan and result.kind != "question":
            from ..observability import run_trace
            run_trace.note("PLAN   (written before building)\n" + plan)
            self.session.add_assistant_message("PLAN - what will be built:\n" + plan)
        return result

    def _ask_ai(self, system: str, user: str) -> str:
        """One plain question to the AI picked in the panel (no tools). Quota gone: waits for it, then asks again."""
        from ..agent.models import Message, ModelRequest
        provider = getattr(self._agent, "_model_provider", None)
        while True:
            try:
                response = provider.generate(ModelRequest(messages=[Message(role="system", content=system),
                                                                    Message(role="user", content=user)],
                                                          temperature=0.2))
                return getattr(response, "content", "") or ""
            except Exception as exc:  # noqa: BLE001
                if not self._wait_for_quota(str(exc)):
                    raise

    def _ai_ready(self) -> bool:
        provider = getattr(self._agent, "_model_provider", None)
        return callable(getattr(provider, "generate", None)) and \
            getattr(self, "current_provider_name", "mock") not in ("mock", "")

    def _arrange(self, user_input: str, session) -> str:
        """After the build: the AI decides where every checklist thing goes best (the user's positions win), the agent
        moves them and undoes it if the scene got worse."""
        understanding = getattr(self, "_understanding", None)
        if understanding is None or understanding.kind != "new" or len(understanding.checklist) < 2 \
                or self._cancelled or not self._ai_ready() or not getattr(self, "ai_placement", True):
            return ""
        bridge = getattr(self._verifier, "bridge", None) if self._verifier is not None else None
        if bridge is None or not hasattr(bridge, "scene_snapshot"):
            return ""
        from ..agent.arrange import Arranger
        from ..observability import run_trace
        try:
            baseline = set((getattr(session, "baseline", None) or {}).keys())
            new_objects = {o["name"] for o in bridge.scene_snapshot().get("objects", [])} - baseline
            run_trace.note("PLACE  asking the AI where every thing goes best …")
            from ..observability import token_meter
            token_meter.set_phase("place")
            result = Arranger(bridge, self._ask_ai).arrange(user_input, understanding.checklist, new_objects)
            if result.undone:
                token_meter.mark_waste("placement made things worse - undone", token_meter.phase_tokens("place"))
        except Exception as exc:  # noqa: BLE001 - placement is an improvement, never a reason to fail
            from ..reliability.friendly_errors import is_quota_error
            if is_quota_error(str(exc)) and self._cancelled:
                raise
            self._log("place.failed", error=str(exc)[:300])
            return ""
        self._log("place.done", moved=result.moved, undone=result.undone, before=result.before_high,
                  after=result.after_high, placements=[f"{p.thing} -> {p.location} ({p.why})" for p in result.placements])
        text = result.text()
        run_trace.note("PLACE  " + text)
        self.session.add_assistant_message(text)
        return text

    def _wait_for_quota(self, error: str) -> bool:
        """The picked AI's quota / rate limit is used up: wait until it is back (True = try again now). False when it
        is not a quota problem, Stop was pressed, or waiting cannot help (a bad key, a request that never fits)."""
        from ..reliability.friendly_errors import friendly_error_message, is_quota_error
        if not is_quota_error(error) or self._cancelled:
            return False
        from .quota_wait import QuotaWaiter
        waiter = getattr(self, "_quota_waiter", None)
        label = {"gemini": "Gemini", "claude": "Claude", "openai": "OpenAI"}.get(
            getattr(self, "current_provider_name", ""), "The AI")
        if waiter is None or waiter.provider_label != label:
            def status(text: str) -> None:
                self.quota_status = text
                try:
                    from . import activity
                    activity.set_check(text)
                except Exception:  # noqa: BLE001
                    pass
            waiter = QuotaWaiter(label, should_stop=lambda: self._cancelled, status=status,
                                 sleep=getattr(self, "_quota_sleep", None), clock=getattr(self, "_quota_clock", None)
                                 or __import__("time").time)
            self._quota_waiter = waiter
        reason = friendly_error_message(error)
        try:
            from ..observability import token_meter
            token_meter.record_failure(getattr(self, "current_provider_name", ""),
                                       getattr(self, "current_model_name", "") or "", error[:200])
        except Exception:  # noqa: BLE001
            pass
        self._log("quota.wait", provider=label, reason=reason[:300])
        self.session.add_assistant_message(f"{reason} Waiting for {label} - the run goes on by itself (Stop cancels).")
        ok = waiter.wait(error)
        self.quota_status = ""
        try:
            from . import activity
            activity.set_check("")
        except Exception:  # noqa: BLE001
            pass
        self._log("quota.resume" if ok else "quota.gave_up", provider=label, waited_s=round(waiter.total_waited))
        return ok

    # (kept for older callers: no other provider is ever used now - it waits for the same one)
    _switch_provider_after_quota = _wait_for_quota

    def cancel(self) -> None:
        self._cancelled = True
        try:
            from .activity import request_stop
            request_stop()
        except Exception:  # noqa: BLE001
            pass