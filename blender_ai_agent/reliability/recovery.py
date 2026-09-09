"""
RecoveryManager — Step 4.7
==============================
Hinglish: Failure ke baad, agar error "recoverable" hai (jaise
OBJECT_NOT_FOUND), ye class ek CORRECTED ToolCall suggest karti hai
— exactly spec ka example: "RedCube" bola gaya tha, scene mein
"Red_Cube" hai, tools dhoond ke sahi naam se retry karega.
"""

from typing import Optional

from ..agent.models import ToolCall
from .errors import ErrorCode, ToolError


class RecoveryManager:

    # In arguments mein se koi bhi "object naam" ho sakta hai
    NAME_ARG_KEYS = ("name", "object_name", "old_name")

    def __init__(self, tool_caller):
        # Dependency Injection — scene inspect karne ke liye ToolCaller use karte hain,
        # BlenderBridge directly nahi (architecture rule follow karte hain).
        self._tool_caller = tool_caller

    def attempt_recovery(self, tool_call: ToolCall, error: ToolError) -> Optional[ToolCall]:
        """
        Hinglish: Agar recovery possible hai, ek NAYA (corrected)
        ToolCall return karta hai — caller (ExecutionLoop/Agent) isko
        retry karega. Agar recovery possible nahi, None return hota hai.
        """
        if error.code != ErrorCode.OBJECT_NOT_FOUND:
            return None  # abhi sirf OBJECT_NOT_FOUND ke liye recovery try karte hain

        arg_key = self._find_name_argument(tool_call)
        if arg_key is None:
            return None

        wrong_name = tool_call.arguments[arg_key]
        correct_name = self._find_similar_object_name(wrong_name)

        if correct_name is None:
            return None

        new_arguments = dict(tool_call.arguments)
        new_arguments[arg_key] = correct_name
        return ToolCall(tool_name=tool_call.tool_name, arguments=new_arguments)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _find_name_argument(self, tool_call: ToolCall) -> Optional[str]:
        for key in self.NAME_ARG_KEYS:
            if key in tool_call.arguments:
                return key
        return None

    def _find_similar_object_name(self, wrong_name: str) -> Optional[str]:
        """
        Hinglish: scene.inspect chalake, "normalized" naam match dhoondta
        hai — case aur underscores/spaces ignore karke. "RedCube" aur
        "Red_Cube" dono normalize hoke "redcube" ban jaate hain.
        """
        result = self._tool_caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        if not result.success:
            return None

        object_names = [obj["name"] for obj in result.data.get("objects", [])]
        wrong_normalized = self._normalize(wrong_name)

        for name in object_names:
            if self._normalize(name) == wrong_normalized:
                return name

        return None

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())