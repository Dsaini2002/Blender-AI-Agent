"""Continue an unfinished run - also with ANOTHER provider.

A run that was stopped (Stop button), failed (an error, a used-up quota) or ended only partly done is remembered here:
its request and the AI's plan (checklist, tools, save wish). The panel then shows "Continue with <provider>": pick any
provider in the dropdown and press it. The new run reuses the plan (no second planning request), looks at what is
already in the scene and builds only what is missing - nothing is built twice, nothing is lost.
"""

import time
from typing import Optional

MARK = "CONTINUE the unfinished request below"

_PENDING: dict = {}


def remember(request: str, understanding, why: str, provider: str = "") -> None:
    """Keep an unfinished run (only one: the last)."""
    original = original_request(request)
    if not original.strip():
        return
    _PENDING.clear()
    _PENDING.update(request=original, understanding=understanding, why=why, provider=provider, time=time.time())


def clear() -> None:
    _PENDING.clear()


def pending() -> Optional[dict]:
    return dict(_PENDING) if _PENDING else None


def original_request(text: str) -> str:
    """The user's own request inside a continuation prompt (continuing twice keeps the original)."""
    import re
    text = re.sub(r"\n\(Scene context:.*?\)\s*$", "", text or "", flags=re.DOTALL)
    if text.startswith(MARK) and "\nOriginal request:\n" in text:
        text = text.split("\nOriginal request:\n", 1)[1]
        text = re.sub(r"\n\(Scene context:.*?\)\s*$", "", text, flags=re.DOTALL)
    return text.strip()


def prompt() -> str:
    """The prompt for the next run: what to do + the original request."""
    if not _PENDING:
        return ""
    checklist = ""
    understanding = _PENDING.get("understanding")
    try:
        from ..agent.checklist import checklist_text
        if understanding is not None and getattr(understanding, "checklist", None):
            checklist = "\nCHECKLIST of the request (count what is already there):\n" + \
                checklist_text(understanding.checklist)
    except Exception:  # noqa: BLE001
        checklist = ""
    return (f"{MARK} - it stopped part-way ({_PENDING.get('why', 'stopped')}). Everything built before is STILL in the "
            "scene: first look at it (scene.inspect / object.measure), compare it with the checklist, then build ONLY "
            "what is missing or wrong and finish the rest of the request (placing, materials, camera, saving). "
            "Never build again what is already there." + checklist + "\nOriginal request:\n" + _PENDING["request"])


def take(user_input: str):
    """When `user_input` is a continuation: the remembered plan to reuse (None otherwise)."""
    if not (user_input or "").startswith(MARK) or not _PENDING:
        return None
    return _PENDING.get("understanding")
