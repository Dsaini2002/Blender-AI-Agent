"""
CopilotController — Step 6.3
================================
Hinglish: UI aur Agent ke beech ka MAIN coordinator.

CRITICAL RULE (Step 6.1): UI business logic nahi karegi, aur
Controller khud bpy nahi chhuyega. Controller sirf:

    UI -> Controller -> Agent (RepairableExecutionLoop) -> ... -> Blender

Controller Agent ke internal implementation (ToolCaller, Registry,
etc.) mein nahi ghusta — sirf `agent.run(user_message, state)` ya
`agent.run(user_message)` jaisa public interface use karta hai.
"""

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
    """Hinglish: submit() ka return value — UI ko dikhane ke liye."""
    reply_text: Optional[str]
    success: bool
    task_id: str = ""


class CopilotController:

    def __init__(self, agent, session: Optional[CopilotSession] = None, skill_registry=None,
                 tool_caller=None, tracker: Optional[ProgressTracker] = None, auto_split: bool = True,
                 split_min_parts: int = 3, split_max_parts: int = 10):
        self._agent = agent
        # Hinglish: Progress + bade task ko steps mein todna. auto_split=False ya request chhoti ho to
        # pehle jaisa hi ek baar mein chalta hai.
        self._tracker = tracker if tracker is not None else get_tracker()
        self._auto_split = auto_split
        self._split_min_parts = split_min_parts
        self._split_max_parts = split_max_parts
        self.session = session if session is not None else CopilotSession()
        self._cancelled = False
        self._conversation_state = ConversationState(system_prompt=SYSTEM_PROMPT)
        # Hinglish: Step "Skill fast-path" — agar SkillRegistry aur
        # ToolCaller diye gaye hain, to submit() pehle dekhta hai ki
        # koi built-in Skill (jaise HouseBuilderSkill) is request ko
        # deterministically handle kar sakti hai. Agar haan, to LLM ko
        # call hi nahi karte — guaranteed, fast, offline-safe result.
        # Match na mile to normal LLM-driven Agent flow chalta hai,
        # jaisa pehle chalta tha (backward compatible — dono None ho
        # sakte hain).
        self._skill_registry = skill_registry
        self._tool_caller = tool_caller

    def submit(self, user_input: str, on_progress=None) -> SubmitResult:
        """
        Hinglish: User ka message Agent ko bhejta hai, result ko
        session mein record karta hai, aur UI ke liye ek simple
        SubmitResult return karta hai.

        `on_progress(event: str, data: dict)` — optional callback,
        jise Blender ka background-thread runner status updates ke
        liye pass karta hai (progress popup mein dikhane ke liye).
        Ye callback plain Python hona chahiye — koi bpy call iske
        andar nahi honi chahiye (background thread se call hoga).

        Agar submit() call hone se PEHLE hi cancel() ho chuka tha,
        Agent ko call hi nahi karte — turant cancelled result de dete hain.

        Bada request (kam se kam 3 alag kaam: lines / "then" / "phir" / numbering) apne aap chhote steps mein
        tootkar EK-EK karke chalta hai; har step ke baad progress (percent + bacha hua time) dikhta hai, aur
        ek step fail ho to baaki chalte rehte hain (har step ka apna rollback hota hai).
        """
        if self._cancelled:
            self.session.add_error_message("Task was cancelled.")
            return SubmitResult(reply_text=None, success=False)

        self.session.add_user_message(user_input)

        parts = self._plan(user_input)
        if len(parts) > 1:
            return self._run_steps(user_input, parts, on_progress)

        # Hinglish: Chhota/single request — bilkul pehle jaisa: on_progress ASLI haath mein logger tak jaata hai
        # (koi wrapper nahi, koi extra call nahi). Sirf tracker mein elapsed time darj hota hai taaki panel
        # "Working 0:12 (usually ~0:20)" dikha sake.
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
    def _plan(self, user_input: str) -> List[str]:
        if not self._auto_split:
            return [user_input]
        return split_task(user_input, min_parts=self._split_min_parts, max_parts=self._split_max_parts)

    def _predict_kind(self, part: str) -> str:
        """'skill' = bina LLM ke tez chalne wala (campfire, tent...), warna 'agent' (LLM wala, dheera)."""
        try:
            if self._skill_registry is not None and self._tool_caller is not None \
                    and self._skill_registry.find_best_match(part) is not None:
                return "skill"
        except Exception:  # noqa: BLE001 — sirf andaza hai, kabhi task na roke
            pass
        return "agent"

    def _progress_callback(self, on_progress):
        """Agent ke logger events ko tracker mein ginta hai aur panel ko ek compact progress line bhejta hai."""
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

    def _run_steps(self, user_input: str, parts: List[str], on_progress) -> SubmitResult:
        tracker = self._tracker
        tracker.begin(user_input, steps=parts, kinds=[self._predict_kind(p) for p in parts])
        callback = self._progress_callback(on_progress)

        plan = tracker.snapshot()
        intro = (f"Is request ko {len(parts)} steps mein baanta gaya — ek-ek karke chalega "
                 f"(andaaza ~{format_duration(plan.eta)}).")
        self.session.add_assistant_message(intro)
        self._push_status(on_progress)

        results: List[SubmitResult] = []
        stopped_reason = ""
        for index, part in enumerate(parts):
            if self._cancelled:
                stopped_reason = "cancelled"
                break

            tracker.start_step(index)
            self._push_status(on_progress)
            try:
                result = self._run_one(part, callback)
            except Exception as exc:  # noqa: BLE001 — ek step ki crash baaki steps ko na roke
                from ..reliability.friendly_errors import friendly_error_message
                result = SubmitResult(reply_text=friendly_error_message(str(exc)), success=False)
                self.session.add_error_message(result.reply_text)

            tracker.finish_step(index, result.success, note="" if result.success else (result.reply_text or "")[:200])
            results.append(result)
            self._push_status(on_progress)

            if not result.success and self._is_quota_text(result.reply_text):
                stopped_reason = "quota"          # quota khatam -> aage ke steps bhi fail honge, rok do
                break

        tracker.skip_remaining(note=stopped_reason or "skipped")
        all_ok = len(results) == len(parts) and all(r.success for r in results)
        tracker.finish(ok=all_ok)
        self._push_status(on_progress)

        summary = self._summarize(parts, results, stopped_reason)
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

    def _run_one(self, user_input: str, on_progress=None) -> SubmitResult:
        """Ek hi request/step: pehle Skill fast-path, warna LLM Agent (purana flow, jaisa tha waisa)."""
        skill_result = self._try_skill_fast_path(user_input)
        if skill_result is not None:
            return skill_result

        logger = getattr(self._agent, "_logger", None)
        if logger is not None:
            logger.callback = on_progress

        try:
            run_result = self._agent.run(user_input, state=self._conversation_state)
        except Exception as exc:  # noqa: BLE001
            # Hinglish: Provider ka quota/rate-limit error user ko lamba protobuf dump
            # nahi, ek saaf message dikhana chahiye. Baaki saari exceptions pehle jaisi hi
            # upar jaati hain (worker thread unhe "Unexpected error" ki tarah dikhata hai).
            from ..reliability.friendly_errors import friendly_error_message, is_quota_error
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

        if rolled_back or run_result.reply_text is None:
            error_text = run_result.reply_text or "Task could not be completed."
            self.session.add_error_message(error_text, metadata={"task_id": task_id})
            return SubmitResult(reply_text=error_text, success=False, task_id=task_id)

        self.session.add_assistant_message(run_result.reply_text, metadata={"task_id": task_id})
        return SubmitResult(reply_text=run_result.reply_text, success=True, task_id=task_id)

    def _try_skill_fast_path(self, user_input: str) -> Optional[SubmitResult]:
        """
        Hinglish: SkillRegistry mein koi confident match (e.g. "house")
        mile to us Skill ko directly execute karte hain — bina LLM ko
        call kiye. Return None matlab "koi match nahi, normal Agent
        flow use karo".
        """
        if self._skill_registry is None or self._tool_caller is None:
            return None

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
        shown = {k: v for k, v in data.items() if k != "notes"} if notes else skill_result.data

        reply_text = (
            f"Done — built with the '{skill.name}' skill "
            f"({len(skill_result.steps_completed)} steps): {shown}"
        )
        # Hinglish: Skill ke sawaal/notes (jaise "default Cube delete karun?") alag line mein
        # dikhao, raw dict mein dabe hue nahi.
        for note in notes:
            reply_text += f"\n{note}"
        self.session.add_assistant_message(reply_text)
        return SubmitResult(reply_text=reply_text, success=True)

    @staticmethod
    def _extract_skill_context(user_input: str) -> dict:
        """
        Hinglish: Bahut simple, dependency-free color/name extraction —
        koi LLM call nahi. Agar user "red roof", "blue walls" jaisa
        kuch bole, wo HouseBuilderSkill ke context mein pass ho jaata
        hai. Match na mile to Skill apne defaults use karti hai.
        """
        _COLOR_MAP = {
            "red": [0.7, 0.1, 0.1, 1.0], "blue": [0.15, 0.35, 0.75, 1.0],
            "green": [0.15, 0.55, 0.2, 1.0], "yellow": [0.9, 0.8, 0.1, 1.0],
            "white": [0.95, 0.95, 0.95, 1.0], "black": [0.05, 0.05, 0.05, 1.0],
            "brown": [0.4, 0.25, 0.12, 1.0], "pink": [0.9, 0.5, 0.6, 1.0],
            "purple": [0.4, 0.15, 0.55, 1.0], "orange": [0.85, 0.45, 0.1, 1.0],
            "grey": [0.5, 0.5, 0.5, 1.0], "gray": [0.5, 0.5, 0.5, 1.0],
        }
        text = user_input.lower()
        context: dict = {"task": user_input}  # Hinglish: library_props skill ko asli request text chahiye

        # Hinglish: "delete the default cube" / "remove the cube and light" jaisa
        # explicit kehna = user ki permission. Tabhi skill startup Cube/Light delete karti hai.
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

    def cancel(self) -> None:
        """
        Hinglish: Abhi ke liye simple flag hai — poora cooperative
        cancellation (Agent ko beech mein rokna) TransactionManager
        ke saath deeper integration maangta hai, jo future refinement
        hai. Abhi ye "next submit ka result discard karo" jaisa kaam
        karta hai.
        """
        self._cancelled = True