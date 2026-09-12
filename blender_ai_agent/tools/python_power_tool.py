"""
PythonPowerTool — Step 9.24 / 9.25
=======================================
Hinglish: Raw Python execution ek "power tool" hai — PRIMARY interface
nahi. Sirf tab use hoga jab koi structured tool available na ho.

Safety (9.25):
  - PYTHON_EXECUTION permission (sabse high-risk level)
  - Ek allowlist of safe builtins — dangerous cheezein (import, open,
    eval, exec, __import__) explicitly block hoti hain
  - Execution ek restricted namespace mein hota hai, bridge ke through
    hi Blender access milta hai — global bpy access nahi
"""

from dataclasses import dataclass

from .base import Permission, Tool, ToolResult

# Hinglish: Sirf ye builtins allowed hain — baaki sab block.
_SAFE_BUILTINS = {
    "len": len, "range": range, "list": list, "dict": dict,
    "str": str, "int": int, "float": float, "bool": bool,
    "min": min, "max": max, "sum": sum, "abs": abs,
    "enumerate": enumerate, "zip": zip,
}

_BLOCKED_KEYWORDS = ("import", "exec", "eval", "__", "open(", "os.", "sys.", "subprocess")


@dataclass
class PythonExecutionInput:
    code: str

    def __post_init__(self):
        if not self.code or not isinstance(self.code, str):
            raise ValueError("PythonExecutionInput.code must be a non-empty string")


class PythonPowerTool(Tool):
    name = "python.execute"
    description = "Executes a restricted snippet of Python against the scene bridge. Use only when no structured tool exists."
    permission = Permission.PYTHON_EXECUTION
    input_model = PythonExecutionInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: PythonExecutionInput) -> ToolResult:
        code = validated_input.code

        blocked = self._find_blocked_keyword(code)
        if blocked is not None:
            return ToolResult.fail(f"Code contains blocked keyword: '{blocked}'.")

        restricted_globals = {"__builtins__": _SAFE_BUILTINS}
        restricted_locals = {"bridge": self._bridge, "result": None}

        try:
            exec(code, restricted_globals, restricted_locals)
        except Exception as exc:
            return ToolResult.fail(f"Python execution failed: {exc}")

        return ToolResult.ok({"result": restricted_locals.get("result")})

    @staticmethod
    def _find_blocked_keyword(code: str):
        lowered = code.lower()
        for keyword in _BLOCKED_KEYWORDS:
            if keyword in lowered:
                return keyword
        return None