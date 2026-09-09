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

    def __init__(self):
        self._messages: List[Message] = []

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
        """Poori history ka copy deta hai — caller isse modify na kare."""
        return list(self._messages)

    def __len__(self) -> int:
        return len(self._messages)