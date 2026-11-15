"""Where the walkable strips (paths, roads, sidewalks) are, so nothing gets placed in the middle of one.

curve.create(profile="flat") registers each strip's centre-line and width here. Placement
tools then ask `clear_spot` for a nearby free spot, and the geometry check asks `on_path`
to find props that still block a path. Entries for objects that were deleted are ignored;
an entry follows its object if the object was moved.
"""

import math
from typing import Dict, List, Optional, Sequence, Tuple

_PATHS: Dict[str, dict] = {}

EDGE_GAP = 0.25          # space left between a moved prop and the path edge (m)


def _rotate(x: float, y: float, angle: float) -> Tuple[float, float]:
    c, s = math.cos(angle), math.sin(angle)
    return x * c - y * s, x * s + y * c


def register(name: str, strokes: Sequence[Sequence[Sequence[float]]], width: float,
             location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)) -> None:
    """Remember a flat strip. `strokes` are local centre-lines (already smoothed)."""
    lx, ly = float(location[0]), float(location[1])
    sx, sy = float(scale[0]), float(scale[1])
    yaw = float(rotation[2]) if rotation else 0.0
    world = []
    for stroke in strokes:
        pts = []
        for p in stroke:
            x, y = _rotate(float(p[0]) * sx, float(p[1]) * sy, yaw)
            pts.append((x + lx, y + ly))
        if len(pts) >= 2:
            world.append(pts)
    if world:
        _PATHS[name] = {"strokes": world, "width": float(width) * max(abs(sx), abs(sy)),
                        "origin": (lx, ly)}


def forget(name: str) -> None:
    _PATHS.pop(name, None)


def clear() -> None:
    _PATHS.clear()


def live_paths(bridge=None) -> Dict[str, dict]:
    """Registered paths whose object still exists, shifted if the object was moved since."""
    out = {}
    for name, entry in list(_PATHS.items()):
        dx = dy = 0.0
        if bridge is not None:
            try:
                obj = bridge.get_object(name)
            except Exception:  # noqa: BLE001
                obj = None
            if obj is None:
                continue
            loc = list(getattr(obj, "location", entry["origin"]))
            dx, dy = float(loc[0]) - entry["origin"][0], float(loc[1]) - entry["origin"][1]
        strokes = entry["strokes"] if (dx, dy) == (0.0, 0.0) else \
            [[(x + dx, y + dy) for x, y in stroke] for stroke in entry["strokes"]]
        out[name] = {"strokes": strokes, "width": entry["width"]}
    return out


def _closest_on_segment(px, py, ax, ay, bx, by):
    vx, vy = bx - ax, by - ay
    length2 = vx * vx + vy * vy
    t = 0.0 if length2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / length2))
    qx, qy = ax + t * vx, ay + t * vy
    return qx, qy, (vx, vy)


def nearest(px: float, py: float, paths: Dict[str, dict]) -> Optional[dict]:
    """Closest path point to (px, py): {name, distance, point, direction, half_width}."""
    best = None
    for name, entry in paths.items():
        for stroke in entry["strokes"]:
            for (ax, ay), (bx, by) in zip(stroke, stroke[1:]):
                qx, qy, direction = _closest_on_segment(px, py, ax, ay, bx, by)
                d = math.hypot(px - qx, py - qy)
                if best is None or d < best["distance"]:
                    best = {"name": name, "distance": d, "point": (qx, qy), "direction": direction,
                            "half_width": entry["width"] / 2.0}
    return best


def on_path(px: float, py: float, radius: float, paths: Dict[str, dict]) -> Optional[dict]:
    """The path a round footprint of `radius` at (px, py) overlaps, if any (the most-overlapped one)."""
    worst = None
    for name, entry in paths.items():
        hit = nearest(px, py, {name: entry})
        if hit and hit["distance"] < hit["half_width"] + radius:
            overlap = hit["half_width"] + radius - hit["distance"]
            if worst is None or overlap > worst["overlap"]:
                hit["overlap"] = overlap
                worst = hit
    return worst


def clear_spot(px: float, py: float, radius: float, paths: Dict[str, dict], attempts: int = 5):
    """Move (px, py) sideways out of every path it overlaps. Returns (x, y, [path names it was moved off],
    facing (dx, dy) unit vector from the new spot towards the last path, or None)."""
    x, y = px, py
    moved_off: List[str] = []
    facing = None
    for _ in range(attempts):
        hit = on_path(x, y, radius, paths)
        if hit is None:
            break
        qx, qy = hit["point"]
        nx, ny = x - qx, y - qy
        length = math.hypot(nx, ny)
        if length < 1e-6:                                   # dead centre: go to the left of the direction
            dx, dy = hit["direction"]
            dl = math.hypot(dx, dy) or 1.0
            nx, ny, length = -dy / dl, dx / dl, 1.0
        nx, ny = nx / length, ny / length
        target = hit["half_width"] + radius + EDGE_GAP
        x, y = qx + nx * target, qy + ny * target
        facing = (-nx, -ny)
        if hit["name"] not in moved_off:
            moved_off.append(hit["name"])
    return x, y, moved_off, facing


def facing_yaw_degrees(facing: Tuple[float, float]) -> float:
    """yaw for a model whose front faces -Y (benches) so it looks along `facing`."""
    return math.degrees(math.atan2(facing[0], -facing[1]))
