"""State behind the panel that is not a Blender property: recent tasks (kept on disk), the checkpoint taken
before each run (for "Revert AI changes") and the quick-action prompts. Pure Python, so it is tested
without Blender."""

import json
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional

MAX_RECENT = 12


def recent_path() -> str:
    env = os.environ.get("BLENDER_AI_RECENT_FILE")
    if env:
        return os.path.expanduser(env)
    return os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "recent_tasks.json")


def load_recent(path: Optional[str] = None) -> List[Dict[str, Any]]:
    try:
        with open(path or recent_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return [t for t in data if isinstance(t, dict) and t.get("prompt")][:MAX_RECENT]
    except (OSError, ValueError, TypeError):
        return []


def save_recent(tasks: List[Dict[str, Any]], path: Optional[str] = None) -> None:
    path = path or recent_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(tasks[:MAX_RECENT], handle, indent=1)
    except OSError:
        pass


def classify(reply: str, ok: bool) -> str:
    reply = (reply or "").strip()
    if reply.startswith("Stopped"):
        return "stopped"
    partial = re.match(r"Done (\d+)/(\d+) steps", reply)
    if partial and partial.group(1) != partial.group(2):
        return "partial" if int(partial.group(1)) > 0 else "failed"
    return "completed" if ok else "failed"


def check_line(reply: str) -> str:
    """'Auto-check ✓ fixed after 2 round(s): ... -> vision 9/10' -> a short line for the task card."""
    for line in (reply or "").splitlines():
        line = line.strip()
        if line.startswith("Auto-check"):
            rounds = re.search(r"(\d+) (?:fix )?round", line)
            scores = re.findall(r"vision (\d+(?:\.\d+)?)/10", line)
            bits = []
            if scores:
                bits.append(f"vision {scores[-1]}/10")
            if rounds:
                bits.append(f"{rounds.group(1)} fix round(s)")
            if "✓" in line and not bits:
                bits.append("passed")
            if "skipped" in line and not scores:
                bits.append("vision skipped")
            return "Auto-check: " + ", ".join(bits) if bits else line[:80]
    return ""


def add_task(tasks: List[Dict[str, Any]], prompt: str, reply: str, ok: bool, seconds: Optional[float],
             log: str = "") -> List[Dict[str, Any]]:
    entry = {
        "prompt": prompt.strip(),
        "status": classify(reply, ok),
        "seconds": round(float(seconds), 1) if seconds is not None else None,
        "summary": next((l.strip() for l in (reply or "").splitlines() if l.strip()), "")[:200],
        "check": check_line(reply),
        "log": log or "",
        "when": time.strftime("%Y-%m-%d %H:%M"),
    }
    return [entry] + [t for t in tasks if t.get("prompt") != entry["prompt"]][:MAX_RECENT - 1]


def title(prompt: str, width: int = 34) -> str:
    first = next((l.strip(" -•\t") for l in (prompt or "").splitlines() if l.strip()), "")
    return first if len(first) <= width else first[: width - 1].rstrip() + "…"


STATUS_ICON = {"completed": "CHECKMARK", "partial": "INFO", "failed": "ERROR", "stopped": "CANCEL"}
STATUS_WORD = {"completed": "Completed", "partial": "Partly done", "failed": "Failed", "stopped": "Stopped"}

# ---------------------------------------------------------------- quick actions
QUICK_ACTIONS = {
    "MODELING": ("Modeling", "MESH_DATA",
                 "Add more detail to {target}: real proportions, bevelled edges, smaller parts and trims, so each "
                 "object reads as the real thing. Keep their positions."),
    "MATERIAL": ("Material", "MATERIAL",
                 "Give {target} realistic materials that fit what they are (wood, metal, fabric, stone, glass, "
                 "paint ...), with roughness variation - no plain flat colours."),
    "LIGHTING": ("Lighting", "LIGHT",
                 "Improve the lighting of the scene: a key light, soft fill and rim light, a fitting world / sky, and "
                 "render settings that show {target} clearly with natural contrast."),
}


def quick_prompt(kind: str, selected: List[str]) -> str:
    _label, _icon, template = QUICK_ACTIONS[kind]
    if selected:
        shown = ", ".join(selected[:8]) + (f" (+{len(selected) - 8} more)" if len(selected) > 8 else "")
        target = f"the selected objects ({shown})"
    else:
        target = "every object in the scene"
    return template.format(target=target)


def with_scene_context(prompt: str, selected: List[str], active: Optional[str]) -> str:
    """Tell the agent what 'this' / 'it' / 'the selected' means, without changing short prompts much."""
    if not selected:
        return prompt
    shown = ", ".join(selected[:12]) + (f" (+{len(selected) - 12} more)" if len(selected) > 12 else "")
    extra = f"\n(Scene context: selected objects: {shown}" + (f"; active: {active}" if active else "") + \
            ". When the request says this / it / selected, it means these.)"
    return prompt + extra


# ---------------------------------------------------------------- checkpoint
_CHECKPOINT: Dict[str, Any] = {}


def checkpoint_file() -> str:
    folder = os.path.join(tempfile.gettempdir(), "blender_ai_agent")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "checkpoint.blend")


def take_checkpoint(bridge, prompt: str) -> str:
    """Remember the scene before a run. Returns 'full' (objects saved to a .blend), 'basic' (transforms,
    materials, modifiers only) or '' (nothing could be saved)."""
    _CHECKPOINT.clear()
    _CHECKPOINT["prompt"] = prompt
    save = getattr(bridge, "save_checkpoint", None)
    if callable(save):
        try:
            path = checkpoint_file()
            _CHECKPOINT["file"], _CHECKPOINT["info"] = path, save(path)
            _CHECKPOINT["mode"] = "full"
            return "full"
        except Exception:  # noqa: BLE001 — fall back to the basic snapshot
            _CHECKPOINT.pop("file", None)
    try:
        from ..reliability.snapshot import SnapshotManager
        _CHECKPOINT["snapshot"] = SnapshotManager(bridge).capture()
        _CHECKPOINT["mode"] = "basic"
        return "basic"
    except Exception:  # noqa: BLE001
        _CHECKPOINT.clear()
        return ""


def has_checkpoint() -> bool:
    return bool(_CHECKPOINT.get("mode"))


def checkpoint_prompt() -> str:
    return _CHECKPOINT.get("prompt", "")


def revert(bridge) -> str:
    """Put the scene back as it was before the last run. Returns a short message for the user."""
    mode = _CHECKPOINT.get("mode")
    if not mode:
        return "Nothing to revert."
    if mode == "full":
        try:
            result = bridge.restore_checkpoint(_CHECKPOINT["file"], _CHECKPOINT["info"])
            _CHECKPOINT.clear()
            return f"Reverted: the scene is back as before ({len(result.get('restored', []))} objects)."
        except Exception as exc:  # noqa: BLE001
            return f"Could not revert: {exc}"
    from ..reliability.rollback import RollbackManager
    report = RollbackManager(bridge).rollback_to(_CHECKPOINT["snapshot"])
    _CHECKPOINT.clear()
    message = f"Reverted: removed {len(report.deleted_new_objects)} new object(s), restored {len(report.restored_transforms)}."
    if report.could_not_restore:
        message += f" Could not bring back: {', '.join(report.could_not_restore[:5])}."
    return message
