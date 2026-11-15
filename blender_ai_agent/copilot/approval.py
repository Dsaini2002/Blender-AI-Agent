"""Ask the user before risky tool calls (Python code, deleting objects that existed before the request).

The agent runs in a worker thread; ApprovalGate.request() blocks that thread until the Blender UI answers
(Allow / Deny buttons in the panel) or the timeout passes (= deny). Pure Python, thread-safe, no bpy.
"""

import threading
from typing import Callable, Iterable, Optional

from ..autonomy.modes import AutonomyMode, AutonomyPolicy
from ..tools.base import Permission


class ApprovalGate:

    def __init__(self):
        self._lock = threading.Lock()
        self._pending: Optional[dict] = None
        self._allow_all = False

    def reset(self) -> None:
        """New request: forget an earlier 'Allow all'."""
        with self._lock:
            self._allow_all = False

    def allow_all(self) -> None:
        """Allow this question and every later one in the same request."""
        with self._lock:
            self._allow_all = True
        self.answer(True)

    def request(self, question: str, timeout: float = 300.0) -> bool:
        with self._lock:
            if self._allow_all:
                return True
        event = threading.Event()
        item = {"question": question, "event": event, "allowed": False}
        with self._lock:
            if self._pending is not None:                  # one question at a time
                self._pending["event"].set()
            self._pending = item
        event.wait(timeout)
        with self._lock:
            if self._pending is item:
                self._pending = None
        return bool(item["allowed"])

    def pending_question(self) -> Optional[str]:
        with self._lock:
            return self._pending["question"] if self._pending else None

    def answer(self, allowed: bool) -> None:
        with self._lock:
            item, self._pending = self._pending, None
        if item is not None:
            item["allowed"] = bool(allowed)
            item["event"].set()


def _describe(tool_call) -> str:
    try:
        from .activity import tool_label
        label = tool_label(tool_call.tool_name)
    except Exception:  # noqa: BLE001
        label = tool_call.tool_name
    arguments = tool_call.arguments or {}
    target = arguments.get("name") or arguments.get("object_name") or arguments.get("model") or arguments.get("request")
    return f"{label}" + (f": '{str(target)[:60]}'" if target else "")


def approval_question(tool_call, tool, preexisting: Iterable[str], mode: AutonomyMode = AutonomyMode.ASSISTED) -> Optional[str]:
    """None = run without asking; otherwise the question to show the user.

    MANUAL      ask before every step that changes the scene
    ASSISTED    ask before Python code and before deleting objects the user already had (default)
    AUTONOMOUS  ask only before Python code
    """
    permission = getattr(tool, "permission", None)
    if permission is None or permission == Permission.READ_ONLY:
        return None
    arguments = tool_call.arguments or {}
    if permission == Permission.PYTHON_EXECUTION:
        code = str(arguments.get("code", "")).strip().splitlines()
        preview = "\n".join(line[:70] for line in code[:4]) + ("\n…" if len(code) > 4 else "")
        return f"The AI wants to run Python code:\n{preview}"
    if not AutonomyPolicy(mode).requires_confirmation(permission):
        return None
    if mode == AutonomyMode.MANUAL:
        return f"Next step — {_describe(tool_call)}"
    if permission == Permission.DESTRUCTIVE:
        target = arguments.get("name") or arguments.get("object_name")
        if target and target not in set(preexisting):
            return None                                   # removing something it made in this request
        return f"The AI wants to delete your object '{target}'." if target else f"The AI wants to run {tool_call.tool_name}."
    return None


def make_approver(gate: ApprovalGate, preexisting: Iterable[str], mode: AutonomyMode = AutonomyMode.ASSISTED) -> Callable:
    names = set(preexisting)
    gate.reset()

    def approver(tool_call, tool) -> Optional[str]:
        question = approval_question(tool_call, tool, names, mode)
        if question is None:
            return None
        return None if gate.request(question) else "the user did not allow it"

    return approver


_gate: Optional[ApprovalGate] = None


def get_gate() -> ApprovalGate:
    global _gate
    if _gate is None:
        _gate = ApprovalGate()
    return _gate
