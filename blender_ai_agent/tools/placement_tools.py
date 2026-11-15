"""Placement tools: exact positioning from real bounding boxes, so the model never has to guess coordinates.

object.measure        world bounding box (min / max / size / center) of one or more objects
object.place_on       put an object on top of another (bottom touches the target's top surface)
object.place_next_to  put an object beside another (left / right / front / back), touching or with a gap
object.snap_to_ground make objects rest on the ground (z = 0) or on top of a named ground object

The geometry is pure Python (bridge.measure_objects returns world-space boxes, bridge.transform_object moves).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .base import Permission, Tool, ToolResult

SIDES = {
    "left": (0, -1), "right": (0, 1),
    "front": (1, -1), "back": (1, 1),
    "-x": (0, -1), "+x": (0, 1), "-y": (1, -1), "+y": (1, 1),
}


def box_info(box: Dict[str, List[float]]) -> Dict[str, List[float]]:
    lo, hi = list(box["min"]), list(box["max"])
    return {
        "min": [round(v, 4) for v in lo],
        "max": [round(v, 4) for v in hi],
        "size": [round(hi[k] - lo[k], 4) for k in range(3)],
        "center": [round((hi[k] + lo[k]) / 2.0, 4) for k in range(3)],
    }


def delta_on_top(obj_box, target_box, offset=(0.0, 0.0)) -> List[float]:
    """Move that puts obj's bottom on target's top, centred over target (+ optional x/y offset)."""
    obj, tgt = box_info(obj_box), box_info(target_box)
    return [
        tgt["center"][0] + offset[0] - obj["center"][0],
        tgt["center"][1] + offset[1] - obj["center"][1],
        tgt["max"][2] - obj["min"][2],
    ]


def delta_next_to(obj_box, target_box, side: str, gap: float = 0.0) -> List[float]:
    """Move that puts obj beside target on `side`, touching (+gap), aligned on the other axis, same floor level."""
    axis, sign = SIDES[side]
    obj, tgt = box_info(obj_box), box_info(target_box)
    delta = [0.0, 0.0, tgt["min"][2] - obj["min"][2]]
    other = 1 - axis
    delta[other] = tgt["center"][other] - obj["center"][other]
    if sign > 0:
        delta[axis] = (tgt["max"][axis] + gap) - obj["min"][axis]
    else:
        delta[axis] = (tgt["min"][axis] - gap) - obj["max"][axis]
    return delta


def delta_to_ground(obj_box, ground_z: float) -> List[float]:
    return [0.0, 0.0, ground_z - obj_box["min"][2]]


def _touching(a, b, tolerance: float = 0.05) -> bool:
    return all(a["min"][k] - tolerance <= b["max"][k] and b["min"][k] - tolerance <= a["max"][k] for k in range(3))


def connected_groups(boxes: Dict[str, Dict[str, List[float]]], tolerance: float = 0.05) -> List[List[str]]:
    """Objects whose boxes touch or overlap form one group (tree trunk + crown, chair seat + legs). A group is moved
    as one piece, so a multi-part model never gets pulled apart."""
    names = list(boxes)
    parent = {n: n for n in names}

    def find(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if _touching(boxes[a], boxes[b], tolerance):
                parent[find(a)] = find(b)
    groups: Dict[str, List[str]] = {}
    for n in names:
        groups.setdefault(find(n), []).append(n)
    return list(groups.values())


class _PlacementTool(Tool):
    permission = Permission.SAFE_WRITE

    def __init__(self, bridge):
        self._bridge = bridge

    def _box(self, name: str):
        if self._bridge.get_object(name) is None:
            raise ValueError(f"Object '{name}' not found")
        box = self._bridge.measure_objects([name])
        if box is None:
            raise ValueError(f"Object '{name}' has no geometry to measure")
        return box

    def _move(self, name: str, delta: List[float]) -> List[float]:
        obj = self._bridge.get_object(name)
        location = [float(v) for v in obj.location]
        new_location = [round(location[k] + delta[k], 5) for k in range(3)]
        self._bridge.transform_object(name, location=new_location)
        return new_location


@dataclass
class MeasureInput:
    names: List[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.names, str):
            self.names = [self.names]
        self.names = [str(n) for n in (self.names or []) if str(n).strip()]
        if not self.names:
            raise ValueError("object.measure needs at least one object name in `names`")


class MeasureObjectsTool(_PlacementTool):
    name = "object.measure"
    description = (
        "Returns the real world-space bounding box of objects: min, max, size and center (metres). Use it before "
        "placing things relative to existing objects instead of guessing sizes. `names` = list of object names."
    )
    permission = Permission.READ_ONLY
    input_model = MeasureInput

    def run(self, v: MeasureInput) -> ToolResult:
        result, missing = {}, []
        for name in v.names:
            try:
                result[name] = box_info(self._box(name))
            except ValueError:
                missing.append(name)
        if not result:
            return ToolResult.fail(f"None of these objects could be measured: {', '.join(missing)}")
        data = {"objects": result}
        if len(result) > 1:
            boxes = [self._box(n) for n in result]
            data["combined"] = box_info({
                "min": [min(b["min"][k] for b in boxes) for k in range(3)],
                "max": [max(b["max"][k] for b in boxes) for k in range(3)],
            })
        if missing:
            data["not_found"] = missing
        return ToolResult.ok(data)


@dataclass
class PlaceOnInput:
    name: str
    target: str
    offset: List[float] = field(default_factory=lambda: [0.0, 0.0])

    def __post_init__(self):
        if not self.name or not self.target:
            raise ValueError("object.place_on needs `name` (object to move) and `target` (object to put it on)")
        if self.name == self.target:
            raise ValueError("object.place_on: `name` and `target` must be different objects")
        offset = list(self.offset or [0.0, 0.0])[:2]
        self.offset = [float(x) for x in offset] + [0.0] * (2 - len(offset))


class PlaceOnTool(_PlacementTool):
    name = "object.place_on"
    description = (
        "Puts object `name` exactly ON TOP of object `target`: its bottom touches the target's top surface, centred "
        "over the target, optionally shifted by `offset` [dx, dy] in metres. Use for book on table, lamp on desk, "
        "vase on shelf, roof on walls. No coordinate maths needed."
    )
    input_model = PlaceOnInput

    def run(self, v: PlaceOnInput) -> ToolResult:
        delta = delta_on_top(self._box(v.name), self._box(v.target), v.offset)
        location = self._move(v.name, delta)
        return ToolResult.ok({"name": v.name, "on": v.target, "location": location,
                              "box": box_info(self._box(v.name))})


@dataclass
class PlaceNextToInput:
    name: str
    target: str
    side: str = "right"
    gap: float = 0.0

    def __post_init__(self):
        if not self.name or not self.target:
            raise ValueError("object.place_next_to needs `name` and `target`")
        if self.name == self.target:
            raise ValueError("object.place_next_to: `name` and `target` must be different objects")
        self.side = str(self.side or "right").strip().lower()
        if self.side not in SIDES:
            raise ValueError(f"object.place_next_to: side must be one of left, right, front, back (got '{self.side}')")
        self.gap = max(0.0, float(self.gap or 0.0))


class PlaceNextToTool(_PlacementTool):
    name = "object.place_next_to"
    description = (
        "Puts object `name` BESIDE object `target` on `side` (left = -X, right = +X, front = -Y, back = +Y), touching "
        "it (or `gap` metres apart), centred on the other axis and standing on the same floor level. Use for chair "
        "next to table, shelf against a wall, cars in a row."
    )
    input_model = PlaceNextToInput

    def run(self, v: PlaceNextToInput) -> ToolResult:
        delta = delta_next_to(self._box(v.name), self._box(v.target), v.side, v.gap)
        location = self._move(v.name, delta)
        return ToolResult.ok({"name": v.name, "next_to": v.target, "side": v.side, "location": location,
                              "box": box_info(self._box(v.name))})


@dataclass
class SnapToGroundInput:
    names: List[str] = field(default_factory=list)
    ground: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.names, str):
            self.names = [self.names]
        self.names = [str(n) for n in (self.names or []) if str(n).strip()]
        if not self.names:
            raise ValueError("object.snap_to_ground needs at least one object name in `names`")


class SnapToGroundTool(_PlacementTool):
    name = "object.snap_to_ground"
    description = (
        "Makes objects rest exactly on the ground: the lowest point moves to z = 0, or onto the top of the object named "
        "`ground` (a floor / terrain plane). Parts that touch each other (a tree's trunk and crown, a chair's legs and "
        "seat) move together as one piece, so models are never pulled apart. Fixes floating or sunken objects."
    )
    input_model = SnapToGroundInput

    def run(self, v: SnapToGroundInput) -> ToolResult:
        ground_z = 0.0
        if v.ground:
            ground_z = box_info(self._box(v.ground))["max"][2]
        moved, missing, boxes = {}, [], {}
        for name in v.names:
            if name == v.ground:
                continue
            try:
                boxes[name] = self._box(name)
            except ValueError:
                missing.append(name)
        for group in connected_groups(boxes):
            bottom = min(boxes[n]["min"][2] for n in group)
            delta = [0.0, 0.0, ground_z - bottom]
            for name in group:
                moved[name] = self._move(name, delta)
        if not moved:
            return ToolResult.fail(f"No objects were moved (not found: {', '.join(missing) or '-'})")
        data = {"ground_z": round(ground_z, 4), "moved": moved}
        if missing:
            data["not_found"] = missing
        return ToolResult.ok(data)


def settle_on_support(bridge, names: List[str], tolerance: float = 0.08) -> float:
    """After placing a multi-part model: if it hangs in the air with nothing under it, lower the whole model onto
    the ground (z = 0). Something under it (a table, a floor slab) = left where it is. Returns the drop applied."""
    measure = getattr(bridge, "measure_objects", None)
    if measure is None or not names:
        return 0.0
    try:
        box = measure(list(names))
    except Exception:  # noqa: BLE001
        return 0.0
    if not box or box["min"][2] <= tolerance:
        return 0.0
    bottom, mine = box["min"][2], set(names)
    try:
        others = [o.name for o in bridge.get_objects()
                  if o.name not in mine and getattr(o, "type", "MESH") in ("MESH", "CURVE", "SURFACE", "META", "FONT")]
    except Exception:  # noqa: BLE001
        others = []
    for other in others[:400]:
        try:
            obox = measure([other])
        except Exception:  # noqa: BLE001
            continue
        if obox and _touching({"min": [box["min"][0], box["min"][1], bottom - tolerance],
                               "max": [box["max"][0], box["max"][1], bottom]}, obox, 0.0):
            return 0.0
    for name in names:
        obj = bridge.get_object(name)
        if obj is not None:
            location = [float(v) for v in obj.location]
            bridge.transform_object(name, location=[location[0], location[1], round(location[2] - bottom, 5)])
    return round(bottom, 4)


def path_blockers(bridge, names: List[str], paths_map=None) -> List[dict]:
    """Models (connected groups of the given objects) that stand on a registered path.
    Flat things (the paths themselves, ground, plazas) are ignored. Each item:
    {names, path, center, radius, target} where target is a free spot at the path's edge."""
    from . import paths as _paths

    live = paths_map if paths_map is not None else _paths.live_paths(bridge)
    if not live:
        return []
    boxes = {}
    for name in names:
        if name in live:
            continue
        try:
            box = bridge.measure_objects([name])
        except Exception:  # noqa: BLE001
            box = None
        if not box:
            continue
        height = box["max"][2] - box["min"][2]
        footprint = (box["max"][0] - box["min"][0]) * (box["max"][1] - box["min"][1])
        if height < 0.5 and footprint > 4.0:
            continue                                    # ground, plaza, pond: part of the layout, not a prop
        boxes[name] = box
    out = []
    for group in connected_groups(boxes):
        if min(boxes[n]["min"][2] for n in group) > 0.3:
            continue                                    # hangs above the path (a sign, a branch): fine
        if max(boxes[n]["max"][2] for n in group) - min(boxes[n]["min"][2] for n in group) < 0.15:
            continue                                    # flat decal-like bits
        lo = [min(boxes[n]["min"][k] for n in group) for k in range(2)]
        hi = [max(boxes[n]["max"][k] for n in group) for k in range(2)]
        cx, cy = (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
        trunks = [n for n in group if "trunk" in n.lower() or "pole" in n.lower()]
        if trunks:
            t = boxes[trunks[0]]
            cx, cy = (t["min"][0] + t["max"][0]) / 2.0, (t["min"][1] + t["max"][1]) / 2.0
            radius = min(0.5 * max(t["max"][0] - t["min"][0], t["max"][1] - t["min"][1]), 0.8)
        else:
            radius = min(0.5 * min(hi[0] - lo[0], hi[1] - lo[1]), 1.0)
        hit = _paths.on_path(cx, cy, radius * 0.6, live)   # a small overlap at the very edge is fine
        if hit is None:
            continue
        x, y, _moved, _facing = _paths.clear_spot(cx, cy, radius, live)
        out.append({"names": sorted(group), "path": hit["name"], "center": (cx, cy), "radius": radius,
                    "target": (round(x, 3), round(y, 3))})
    return out


@dataclass
class MoveOffPathInput:
    names: List[str] = field(default_factory=list)

    def __post_init__(self):
        if isinstance(self.names, str):
            self.names = [self.names]
        self.names = [str(n) for n in (self.names or []) if str(n).strip()]
        if not self.names:
            raise ValueError("object.move_off_path needs object names in `names` (all parts of the models to check)")


class MoveOffPathTool(_PlacementTool):
    name = "object.move_off_path"
    description = (
        "Moves props that stand in the middle of a path / road / sidewalk (made with curve.create profile='flat') to "
        "the path's edge. Give all parts of the models to check in `names`; parts that touch (a bench's slats and "
        "legs, a tree's trunk and crown) move together. Objects not on a path are left alone."
    )
    input_model = MoveOffPathInput

    def run(self, v: MoveOffPathInput) -> ToolResult:
        missing = [n for n in v.names if self._bridge.get_object(n) is None]
        present = [n for n in v.names if n not in missing]
        blockers = path_blockers(self._bridge, present)
        moved = []
        for item in blockers:
            dx, dy = item["target"][0] - item["center"][0], item["target"][1] - item["center"][1]
            for name in item["names"]:
                self._move(name, [dx, dy, 0.0])
            moved.append({"parts": item["names"][:6] + (["..."] if len(item["names"]) > 6 else []),
                          "off": item["path"], "moved_by": [round(dx, 3), round(dy, 3)]})
        data = {"moved": moved, "checked": len(present)}
        if missing:
            data["not_found"] = missing
        if not moved:
            data["note"] = "Nothing given stands on a path."
        return ToolResult.ok(data)
