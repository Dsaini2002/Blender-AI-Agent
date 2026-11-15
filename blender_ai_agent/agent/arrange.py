"""Placement: after everything is built, the AI decides where each checklist item goes best.

The agent measures every built thing (real boxes, not guesses) and sends the AI: the checklist with the positions the
user gave, each copy's size and where it is now, and what is around it (floor, walls, the other furniture). The AI
answers with the bottom-centre spot for every thing that should move (+ an optional turn). The agent moves each thing
as one piece (all its parts), then measures again: if the moves made the scene worse (more overlaps / floating /
through walls), every move is undone.
"""

import json
import math
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

ARRANGE_PROMPT = """You arrange objects in a Blender scene (metres, Z up). Everything is already built; you decide
WHERE each listed thing goes. Answer with ONE JSON object only:
{"placements": [{"thing": "book_2", "location": [x, y, z], "turn_degrees": 0, "why": "on the table, next to book_1"}]}
- "thing" = a name from THINGS. location = where its BOTTOM CENTRE must be (z = height of its bottom).
- The user's positions are the law ("on the table" -> z = the table's top, x/y fully inside the table top;
  "left of the sofa" -> smaller x than the sofa ...). Only when the user gave no position, pick the best real-world spot.
- Things ON a surface: bottom z = that surface's top, the whole footprint inside the top, not touching each other
  (keep >= 3 cm between them), in a sensible arrangement (books stacked or side by side, a laptop in front, a lamp
  at the back corner).
- Things on the floor: bottom z = the floor's top; never inside / through a wall; inside the room; >= 5 cm from
  each other; furniture against a wall stands 2-5 cm from it, facing into the room.
- turn_degrees = an extra turn around Z (positive = counter-clockwise), 0 to keep the current turn.
- Leave out things that are already well placed. Never move walls, floor, ceiling, camera or lights.
"""


@dataclass
class Placement:
    thing: str
    location: List[float]
    turn: float = 0.0
    why: str = ""


@dataclass
class ArrangeResult:
    moved: List[str] = field(default_factory=list)
    undone: bool = False
    note: str = ""
    before_high: int = 0
    after_high: int = 0
    placements: List[Placement] = field(default_factory=list)

    def text(self) -> str:
        if self.undone:
            return f"Placement: the AI's moves made the scene worse ({self.before_high} -> {self.after_high} " \
                   f"serious problems) - undone, kept as built."
        if not self.moved:
            return f"Placement: {self.note or 'everything was already in a good place.'}"
        return f"Placement: the AI moved {len(self.moved)} thing(s) to better spots: {', '.join(self.moved[:8])}."


def _bottom_centre(box: dict) -> List[float]:
    return [(box["min"][0] + box["max"][0]) / 2.0, (box["min"][1] + box["max"][1]) / 2.0, box["min"][2]]


def _fmt(values) -> str:
    return "[" + ", ".join(f"{v:.3f}" for v in values) + "]"


def things_for(matches: List[dict], new_objects: Optional[set] = None) -> Dict[str, dict]:
    """thing name -> {item, objects, box}. Only things built in this request (new_objects) can be moved."""
    things = {}
    for entry in matches:
        item = entry["item"]
        for number, copy in enumerate(entry["copies"], 1):
            if new_objects is not None and not any(n in new_objects for n in copy["objects"]):
                continue
            label = re.sub(r"[^a-z0-9]+", "_", item.name.lower()).strip("_") or "thing"
            name = f"{label}_{number}" if len(entry["copies"]) > 1 or item.count > 1 else label
            while name in things:
                name += "_b"
            things[name] = {"item": item, "objects": copy["objects"], "box": copy["box"]}
    return things


def describe(things: Dict[str, dict], snapshot: dict) -> str:
    from ..diagnostics.scene_audit import STRUCTURE, _size
    lines = ["THINGS (you may move these):"]
    for name, thing in things.items():
        box, item = thing["box"], thing["item"]
        where = f' user said: "{item.position}"' if item.position else " user said nothing about where"
        lines.append(f"- {name} ({item.name}): size {_fmt(_size(box))}, bottom centre now {_fmt(_bottom_centre(box))};"
                     f"{where}")
    moving = {n for t in things.values() for n in t["objects"]}
    others = []
    for obj in snapshot.get("objects", []):
        if obj["name"] in moving or not obj.get("box") or obj.get("type") not in ("MESH", "CURVE", "SURFACE", "META"):
            continue
        box = obj["box"]
        size = _size(box)
        kind = "STRUCTURE" if STRUCTURE.search(obj["name"]) else "object"
        others.append((size[0] * size[1] * max(size[2], 0.01), f"- {obj['name']} ({kind}): min {_fmt(box['min'])} "
                                                                f"max {_fmt(box['max'])}"))
    others.sort(key=lambda pair: -pair[0])
    lines.append("AROUND THEM (do not move; use their tops / sides):")
    lines += [text for _, text in others[:40]]
    return "\n".join(lines)


def parse_placements(text: str, things: Dict[str, dict]) -> List[Placement]:
    raw = (text or "").replace("```json", "").replace("```", "")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw[start:end + 1]))
    except ValueError:
        return []
    out = []
    for entry in (data.get("placements") or []) if isinstance(data, dict) else []:
        if not isinstance(entry, dict) or entry.get("thing") not in things:
            continue
        try:
            location = [float(v) for v in list(entry.get("location"))[:3]]
            turn = float(entry.get("turn_degrees", 0) or 0)
        except (TypeError, ValueError):
            continue
        if len(location) != 3 or any(not math.isfinite(v) or abs(v) > 1000 for v in location):
            continue
        out.append(Placement(entry["thing"], location, turn if abs(turn) <= 360 else 0.0, str(entry.get("why", ""))[:160]))
    return out


def _high_count(bridge, request: str) -> int:
    from ..diagnostics.scene_audit import find_errors
    try:
        return sum(1 for f in find_errors(bridge.scene_snapshot(), request) if f["severity"] == "high"
                   and f["kind"] in ("OVERLAP", "THROUGH WALL", "FLOATING", "SUNK", "OUTSIDE ROOM", "NOT ON WALL"))
    except Exception:  # noqa: BLE001
        return 0


class Arranger:

    def __init__(self, bridge, ask: Callable[[str, str], str]):
        self.bridge = bridge
        self.ask = ask

    def _move(self, thing: dict, placement: Placement, undo: list) -> None:
        box = thing["box"]
        here = _bottom_centre(box)
        delta = [placement.location[k] - here[k] for k in range(3)]
        turn = math.radians(placement.turn)
        cx, cy = here[0], here[1]
        names = set(thing["objects"])
        for name in thing["objects"]:
            obj = self.bridge.get_object(name)
            if obj is None:
                continue
            parent = getattr(obj, "parent", None)
            if parent is not None and getattr(parent, "name", None) in names:
                continue                                   # it moves with its parent
            location = [float(v) for v in list(obj.location)[:3]]
            rotation = [float(v) for v in list(getattr(obj, "rotation_euler", [0, 0, 0]))[:3]]
            undo.append((name, list(location), list(rotation)))
            x, y = location[0], location[1]
            if turn:
                dx, dy = x - cx, y - cy
                x = cx + dx * math.cos(turn) - dy * math.sin(turn)
                y = cy + dx * math.sin(turn) + dy * math.cos(turn)
                rotation[2] += turn
            new = [round(x + delta[0], 4), round(y + delta[1], 4), round(location[2] + delta[2], 4)]
            self.bridge.transform_object(name, location=new, rotation=rotation if turn else None)

    def arrange(self, request: str, checklist, new_objects: Optional[set] = None) -> ArrangeResult:
        from .checklist import match_items
        result = ArrangeResult()
        snapshot = self.bridge.scene_snapshot()
        things = things_for(match_items(checklist, snapshot), new_objects)
        if not things:
            result.note = "nothing from the checklist was found to place"
            return result
        user = f"REQUEST: {request}\n\n{describe(things, snapshot)}"
        placements = parse_placements(self.ask(ARRANGE_PROMPT, user), things)
        result.placements = placements
        if not placements:
            result.note = "the AI kept every thing where it was built"
            return result
        result.before_high = _high_count(self.bridge, request)
        undo: list = []
        for placement in placements:
            self._move(things[placement.thing], placement, undo)
            result.moved.append(placement.thing)
        result.after_high = _high_count(self.bridge, request)
        if result.after_high > result.before_high:
            for name, location, rotation in reversed(undo):
                self.bridge.transform_object(name, location=location, rotation=rotation)
            result.undone = True
            result.moved = []
        return result
