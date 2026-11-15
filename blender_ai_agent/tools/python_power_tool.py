"""PythonPowerTool"""

from dataclasses import dataclass

from .base import Permission, Tool, ToolResult

_BLOCKED_KEYWORDS = (
    "exec(", "eval(", "compile(", "__", "open(", "os.", "sys.", "subprocess",
    "socket", "urllib", "requests", "shutil", "pathlib",
    "getattr", "setattr", "delattr", "globals", "locals", "vars(",
    "bpy.data", "blend_data", ".remove(", "unlink(", "bpy.ops.wm.", "bpy.ops.object.delete",
    "window_manager.clipboard",
    ".save(", "save_as", "save_mainfile", "quit_blender",
)

_ALLOWED_IMPORTS = ("import bpy", "import bpy ", "import bpy\n", "from bpy", "import math", "import mathutils", "from mathutils")

_ALLOWED_BPY_PREFIXES = (
    "bpy.ops.mesh.",
    "bpy.ops.object.",
    "bpy.ops.material.",
    "bpy.ops.transform.",
    "bpy.context.",
    "bpy.ops.view3d.blenderkit_search",
    "bpy.ops.scene.blenderkit_download",
)

_ALLOWED_IMPORT_MODULES = {"bpy", "math", "mathutils"}


def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    root_module = name.split(".")[0]
    if root_module not in _ALLOWED_IMPORT_MODULES:
        raise ImportError(f"Import of '{name}' is not allowed inside python.execute")
    import builtins
    return builtins.__import__(name, globals, locals, fromlist, level)


@dataclass
class PythonExecutionInput:
    code: str

    def __post_init__(self):
        if not self.code or not isinstance(self.code, str):
            raise ValueError("PythonExecutionInput.code must be a non-empty string")


class PythonPowerTool(Tool):
    name = "python.execute"
    description = (
        "Executes controlled Blender Python code (bpy.ops.mesh.*, bpy.ops.object.*, "
        "bpy.ops.transform.*, bpy.context.*) for complex geometry that structured tools "
        "don't cover. Use only when no other tool fits. EXPERIMENTAL: if the user's Blender "
        "has the separate BlenderKit addon installed and logged in, this tool can also call "
        "bpy.ops.view3d.blenderkit_search(...) and bpy.ops.scene.blenderkit_download(...) to "
        "fetch external assets — but these are asynchronous (results arrive on a background "
        "thread, not immediately), so check bpy.context.window_manager.blenderkitUI for "
        "completion status across multiple calls rather than assuming one call finishes it."
    )
    permission = Permission.PYTHON_EXECUTION
    input_model = PythonExecutionInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: PythonExecutionInput) -> ToolResult:
        code = validated_input.code

        blocked = self._find_blocked_keyword(code)
        if blocked is not None:
            return ToolResult.fail(f"Code contains blocked keyword: '{blocked}'.")

        if not self._uses_only_allowed_bpy(code):
            return ToolResult.fail(
                "Code must only use bpy.ops.mesh.*, bpy.ops.object.*, "
                "bpy.ops.transform.*, or bpy.context.* — other bpy access is blocked."
            )

        # free-form code can change meshes, materials and names - a FULL checkpoint (every object with its data)
        # brings the scene back exactly if it fails; the light transaction is only the fallback
        checkpoint = self._full_checkpoint()
        from ..reliability.transaction import TransactionManager
        transaction = TransactionManager(self._bridge)
        transaction.begin()

        def _run_in_blender():
            import bpy
            restricted_globals = {
                "__builtins__": {**self._safe_builtins(), "__import__": _restricted_import},
                "bpy": bpy,
            }
            exec(code, restricted_globals, {})

        try:
            # bpy may only be touched on Blender's main thread - the Copilot runs on a worker thread
            from ..bridge.main_thread_dispatch import run_on_main_thread
            run_on_main_thread(_run_in_blender)
        except Exception as exc:
            if checkpoint is not None:
                try:
                    self._bridge.restore_checkpoint(*checkpoint)
                    transaction.commit()
                except Exception:  # noqa: BLE001
                    transaction.rollback()
            else:
                transaction.rollback()
            return ToolResult.fail(f"Python execution failed (rolled back): {exc}")
        finally:
            if checkpoint is not None:
                try:
                    import os
                    os.remove(checkpoint[0])
                except OSError:
                    pass

        transaction.commit()
        return ToolResult.ok({"executed": True})

    def _full_checkpoint(self):
        if not (hasattr(self._bridge, "save_checkpoint") and hasattr(self._bridge, "restore_checkpoint")):
            return None
        try:
            import os
            import tempfile
            path = os.path.join(tempfile.gettempdir(), f"aiagent_pyexec_{os.getpid()}_{id(self)}.blend")
            info = self._bridge.save_checkpoint(path)
            return (path, info) if isinstance(info, dict) else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _find_blocked_keyword(code: str):
        lowered = code.lower()

        for keyword in _BLOCKED_KEYWORDS:
            if keyword.lower() in lowered:
                return keyword

        import re
        for match in re.finditer(r"^\s*(import|from)\s+\S+", code, re.MULTILINE):
            line = match.group(0).strip().lower()
            if not any(line.startswith(allowed.lower().strip()) for allowed in _ALLOWED_IMPORTS):
                return match.group(0).strip()

        return None

    @staticmethod
    def _uses_only_allowed_bpy(code: str) -> bool:
        import re
        bpy_mentions = re.findall(r"bpy\.[a-zA-Z0-9_.]+", code)
        for mention in bpy_mentions:
            if not any(mention.startswith(prefix) for prefix in _ALLOWED_BPY_PREFIXES):
                return False
        return True

    @staticmethod
    def _safe_builtins():
        return {
            "len": len, "range": range, "list": list, "dict": dict,
            "str": str, "int": int, "float": float, "bool": bool,
            "min": min, "max": max, "sum": sum, "abs": abs,
            "enumerate": enumerate, "zip": zip, "print": print,
        }