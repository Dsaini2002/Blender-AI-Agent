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
from typing import Optional

from .messages import MessageRole
from .session import CopilotSession
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
                 tool_caller=None):
        self._agent = agent
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
        """
        if self._cancelled:
            self.session.add_error_message("Task was cancelled.")
            return SubmitResult(reply_text=None, success=False)

        self.session.add_user_message(user_input)

        skill_result = self._try_skill_fast_path(user_input)
        if skill_result is not None:
            return skill_result

        logger = getattr(self._agent, "_logger", None)
        if logger is not None:
            logger.callback = on_progress

        try:
            run_result = self._agent.run(user_input, state=self._conversation_state)
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

        reply_text = (
            f"Done — built with the '{skill.name}' skill "
            f"({len(skill_result.steps_completed)} steps): {skill_result.data}"
        )
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
        context: dict = {}
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