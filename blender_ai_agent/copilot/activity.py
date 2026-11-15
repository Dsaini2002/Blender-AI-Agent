
import threading
import time
from typing import Any, Dict, Optional

_lock = threading.Lock()
_text = ""
_updated = 0.0

TOOL_LABELS = {
    "scene.inspect": "Reading the scene",
    "object.create": "Creating objects",
    "object.delete": "Deleting an object",
    "object.duplicate": "Duplicating an object",
    "object.rename": "Renaming an object",
    "object.transform": "Positioning objects",
    "material.create": "Creating materials",
    "material.assign": "Assigning materials",
    "material.modify": "Adjusting materials",
    "material.nodes": "Building a node material",
    "material.recipe": "Applying a material recipe",
    "render.setup": "Setting up the render",
    "render.preview": "Rendering a preview",
    "vision.observe": "Reviewing the render",
    "modifier.add": "Adding a modifier",
    "modifier.configure": "Configuring a modifier",
    "modifier.remove": "Removing a modifier",
    "camera.create": "Placing the camera",
    "camera.set": "Setting the active camera",
    "light.create": "Adding lights",
    "world.set": "Setting the world",
    "curve.create": "Creating curves",
    "object.move_off_path": "Moving things off the paths",
    "mesh.grandstand": "Building the stands",
    "mesh.field_markings": "Painting the field lines",
    "mesh.create": "Creating a mesh",
    "mesh.damage": "Damaging a mesh",
    "mesh.edit": "Editing a mesh",
    "mesh.script": "Running a mesh formula",
    "mesh.lathe": "Lathing a shape",
    "mesh.sdf": "Sculpting an SDF shape",
    "mesh.terrain": "Generating terrain",
    "mesh.prism": "Creating a prism",
    "character.create": "Building a character",
    "build.iterate": "Build loop",
    "library.place": "Placing a ready-made model",
    "library.list": "Browsing the model library",
    "asset.search_local": "Searching local models",
    "asset.place_local": "Placing a downloaded model",
    "template.build": "Building from a template",
    "retopology.analyze": "Analysing topology",
    "retopology.remesh": "Remeshing",
    "python.execute": "Running Python",
}


def tool_label(tool_name: str) -> str:
    return TOOL_LABELS.get(tool_name or "", tool_name or "a tool")


def describe(event: Any, data: Optional[Dict[str, Any]] = None) -> Optional[str]:
    data = data if isinstance(data, dict) else {}
    name = event if isinstance(event, str) else ""
    if name.startswith("error."):
        name = name[len("error."):]

    tool = data.get("tool")
    if name == "model.request" or (not tool and "turn" in data and "planned_tools" not in data):
        turn = data.get("turn")
        return f"Thinking (turn {turn})" if turn else "Thinking"
    if name == "model.plan" or "planned_tools" in data:
        planned = list(data.get("planned_tools") or [])
        if not planned:
            return None
        first = tool_label(planned[0])
        return f"Planned {len(planned)} step(s): {first}" + ("…" if len(planned) > 1 else "")
    if name == "tool.execute" or (tool and name not in ("tool.failed", "tool.skipped", "repair.retry")):
        return f"Running: {tool_label(tool)}" if tool else None
    if name == "tool.failed":
        return f"Retrying: {tool_label(tool)}" if tool else "Retrying after an error"
    if name == "repair.retry":
        return "Fixing arguments and retrying"
    if name == "tool.skipped":
        return None
    if name == "task.vision_nudge":
        return "Checking the result visually"
    if name == "task.start":
        return "Starting"
    if name == "task.complete":
        return "Finishing up"
    if name.startswith("Planning"):
        return name
    return None


def update(event: Any, data: Optional[Dict[str, Any]] = None) -> None:
    text = describe(event, data)
    if text:
        set_text(text)


def set_text(text: str) -> None:
    global _text, _updated
    with _lock:
        _text = (text or "").strip().replace("\n", " ")
        _updated = time.monotonic()


def get_text() -> str:
    with _lock:
        return _text


def clear() -> None:
    set_text("")
    set_check("")


_check = ""


def set_check(text: str) -> None:
    """What the automatic check is doing ('Auto-check round 2 · vision 6/10'), shown under the progress."""
    global _check
    with _lock:
        _check = (text or "").strip().replace("\n", " ")


def get_check() -> str:
    with _lock:
        return _check


_stop = threading.Event()
_active = threading.Event()


_abandon = threading.Event()        # Stop pressed: the panel is free at once, the old run must not touch anything


def begin_run() -> None:
    """A Copilot request started (UI): Stop requests count only while a run is active."""
    _stop.clear()
    _abandon.clear()
    _active.set()


def abandon() -> None:
    """Stop NOW: the run's next AI wait, tool call or render ends it - even after the panel has moved on."""
    _abandon.set()
    _stop.set()


def run_thread_ended() -> None:
    """The (stopped) run's thread is gone: nothing is left to stop - other buttons may use the tools again."""
    if not _active.is_set():
        _abandon.clear()
        _stop.clear()


def should_stop() -> bool:
    return _abandon.is_set() or (_active.is_set() and _stop.is_set())


def end_run() -> None:
    _active.clear()
    _stop.clear()


def request_stop() -> None:
    if _active.is_set():
        _stop.set()


def clear_stop() -> None:
    _stop.clear()


def stop_requested() -> bool:
    return _active.is_set() and _stop.is_set()
