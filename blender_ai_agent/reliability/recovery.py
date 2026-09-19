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
        if error.code == ErrorCode.MISSING_ARGUMENT:
            return self._recover_missing_argument(tool_call)

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

    def _recover_missing_argument(self, tool_call: ToolCall) -> Optional[ToolCall]:
        """
        Hinglish: LLM ne (aksar) 'name' ya 'object_name' argument
        bhool diya — common case: "create a cylinder" ke turant baad
        "rotate it" bola aur naam repeat nahi kiya. Yahan koi bhi
        "name-jaisa" key already tool_call.arguments mein nahi hai
        (isiliye Python crash hua tha), isliye humein GUESS karna
        padta hai kaunsa argument missing tha.

        Heuristic: object.transform/object.delete/object.rename/
        material.assign jaise tools ke liye, missing naam ka sabse
        sensible default hai — scene mein SABSE RECENTLY CREATE hua
        object (scene.inspect ki list ka aakhri object — naye objects
        end mein add hote hain). Ye exactly us pattern ko fix karta
        hai jo humne dekha: "create X" phir "transform it" (naam repeat
        nahi kiya).
        """
        if tool_call.tool_name not in (
            "object.transform", "object.delete", "object.rename",
            "material.assign", "modifier.add", "modifier.remove", "modifier.configure",
        ):
            return None

        # Agar 'name'/'object_name' already arguments mein hai, ye
        # missing-argument case nahi hai (koi aur field missing thi,
        # jise hum safely guess nahi kar sakte) — recovery skip karo.
        if self._find_name_argument(tool_call) is not None:
            return None

        result = self._tool_caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        if not result.success:
            return None

        objects = result.data.get("objects", [])
        if not objects:
            return None

        most_recent_name = objects[-1]["name"]

        # object.rename ka expected key 'old_name' hai, baaki sab
        # 'name' ya 'object_name' use karte hain (Tool input models).
        target_key = "old_name" if tool_call.tool_name == "object.rename" else (
            "object_name" if tool_call.tool_name in (
                "material.assign", "modifier.add", "modifier.remove", "modifier.configure",
            ) else "name"
        )

        new_arguments = dict(tool_call.arguments)
        new_arguments[target_key] = most_recent_name
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