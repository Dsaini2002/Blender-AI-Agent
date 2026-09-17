"""
ConversationState — Step 3.9
================================
Hinglish: Agent ko conversation "yaad" honi chahiye. Jaise:

    User: "Create a cube."
    Agent: "Done."
    User: "Make it red."   <- "it" = pehle wala cube

Iske liye humein poori message history store karni padti hai, aur
har naye LLM call mein SAARI history bhejni padti hai (na sirf latest
message) — taaki LLM ko context mile.
"""

from typing import List, Optional

from .models import Message
from ..tools.base import ToolResult
from .models import ToolCall


class ConversationState:
    """
    Hinglish: Simple message list wrapper — lekin ek dedicated class
    banane ka fayda: kal agar hume history trimming (bahut lambi ho
    jaaye toh purani messages hatana) ya persistence (disk pe save
    karna) add karni ho, sirf ye ek class badlegi — ExecutionLoop ko
    kuch pata nahi chalega.
    """

    # Hinglish: kitne recent (non-system) messages bhejne hain — TPM
    # budget flat rakhne ke liye. 12 messages = ~6 turns ka context
    # (user/assistant/tool alternating), jo table jaisa 5-6 step task
    # ke liye kaafi hai.
    MAX_RECENT_MESSAGES = 12

    def __init__(self, system_prompt: Optional[str] = None):
        self._messages: List[Message] = []
        if system_prompt:
            self._messages.append(Message(role="system", content=system_prompt))

    def add_user_message(self, content: str) -> None:
        self._messages.append(Message(role="user", content=content))

    def add_assistant_message(self, content: Optional[str]) -> None:
        # Hinglish: content None ho sakta hai jab LLM ne sirf tool_call diya ho,
        # text nahi — is case mein khaali string store karte hain.
        self._messages.append(Message(role="assistant", content=content or ""))

    def add_tool_result_message(self, tool_call: ToolCall, tool_result: ToolResult) -> None:
        """
        Hinglish: Tool chalne ke baad uska result bhi conversation mein
        add hota hai — taaki agle LLM call mein LLM ko pata ho "pichla
        tool call successful raha ya fail hua, aur kya hua".
        """
        if tool_result.success:
            summary = f"Tool '{tool_call.tool_name}' succeeded: {tool_result.data}"
        else:
            summary = f"Tool '{tool_call.tool_name}' failed: {tool_result.error}"

        self._messages.append(Message(role="tool", content=summary))

    def get_messages(self) -> List[Message]:
        """
        Hinglish: Poori history ka copy deta hai — caller isse modify na kare.

        PATCHED (TPM budget fix): Groq free tier ka tokens-per-minute
        budget bahut chhota hai (gpt-oss-20b jaise models pe). Agar hum
        har turn pe POORI, badhti hui history bhejte rahein, token count
        har turn badhta jaata hai aur 429 rate-limit bahut jaldi aane
        lagta hai (real logs mein confirm hua). Isliye ab sirf system
        prompt + last MAX_RECENT_MESSAGES messages bhejte hain — purani
        history "bhool" jaati hai, lekin recent context (jo agle step ke
        decision ke liye zaroori hai) intact rehta hai, aur token
        footprint FLAT rehta hai instead of unbounded growth.
        """
        if not self._messages:
            return []

        system_messages = [m for m in self._messages if m.role == "system"]
        other_messages = [m for m in self._messages if m.role != "system"]

        trimmed = other_messages[-self.MAX_RECENT_MESSAGES:]
        return system_messages + trimmed

    def __len__(self) -> int:
        return len(self._messages)