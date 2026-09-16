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

    def __init__(self, agent, session: Optional[CopilotSession] = None):
        self._agent = agent
        self.session = session if session is not None else CopilotSession()
        self._cancelled = False
        self._conversation_state = ConversationState(system_prompt=SYSTEM_PROMPT)

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

    def cancel(self) -> None:
        """
        Hinglish: Abhi ke liye simple flag hai — poora cooperative
        cancellation (Agent ko beech mein rokna) TransactionManager
        ke saath deeper integration maangta hai, jo future refinement
        hai. Abhi ye "next submit ka result discard karo" jaisa kaam
        karta hai.
        """
        self._cancelled = True