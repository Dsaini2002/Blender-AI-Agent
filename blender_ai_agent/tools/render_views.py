"""render_views.py"""

import math
from typing import Dict, Sequence

VIEW_DIRECTIONS = {
    "front": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0), "right": (1.0, 0.0, 0.0), "left": (-1.0, 0.0, 0.0),
    "top": (0.0, -0.0005, 1.0), "bottom": (0.0, -0.0005, -1.0),
    "three_quarter": (1.0, -1.0, 0.65), "three_quarter_back": (-1.0, 1.0, 0.65),
    "three_quarter_left": (-1.0, -1.0, 0.65), "three_quarter_right_back": (1.0, 1.0, 0.65),
    "low": (0.55, -1.0, 0.12),                  # eye level, from slightly below: sunk / floating / under things
    "wide": (1.0, -1.0, 0.75),                  # zoomed OUT: the whole scene and what is around it
}
VIEW_ZOOM = {"wide": 2.2}                       # distance factor (zoom-in close-ups frame one thing instead)
DEEP_VIEWS = ("front", "back", "left", "right", "top", "three_quarter", "three_quarter_back", "low", "wide")
DEFAULT_FOV = 39.6                       # 50mm lens, 36mm sensor, square render
VIEW_ALIASES = {"side": "right", "3/4": "three_quarter", "iso": "three_quarter", "perspective": "three_quarter", "rear": "back",
                "front_view": "front", "top_view": "top"}


def normalize_view(name: str) -> str:
    key = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    key = VIEW_ALIASES.get(key, key)
    if key not in VIEW_DIRECTIONS:
        raise ValueError(f"unknown view '{name}'. Views: {', '.join(sorted(VIEW_DIRECTIONS))}")
    return key


def camera_pose(bbox_min: Sequence[float], bbox_max: Sequence[float], view: str, fov_degrees: float = DEFAULT_FOV,
                margin: float = 1.2) -> Dict[str, list]:
    view = normalize_view(view)
    margin = margin * VIEW_ZOOM.get(view, 1.0)
    direction = VIEW_DIRECTIONS[view]
    length = math.sqrt(sum(c * c for c in direction))
    unit = [c / length for c in direction]
    centre = [(bbox_min[k] + bbox_max[k]) / 2 for k in range(3)]
    radius = 0.5 * math.sqrt(sum((bbox_max[k] - bbox_min[k]) ** 2 for k in range(3)))
    radius = max(radius, 0.05)
    distance = radius * margin / math.sin(math.radians(fov_degrees) / 2)
    return {"location": [centre[k] + unit[k] * distance for k in range(3)], "target": centre, "distance": distance}

import re as _re

_COVER = _re.compile(r"roof|ceiling|canopy|cover|lid|dome|rafter|truss", _re.IGNORECASE)


def occluders(boxes: Dict[str, dict], bbox_min: Sequence[float], bbox_max: Sequence[float],
              camera_location: Sequence[float]) -> set:
    """Objects that would hide the inside of an enclosed scene from this camera: roofs / ceilings (anything
    flat and large high above the floor) and the tall thin walls on the camera's side. A check render of a
    hall otherwise shows only the outside of its walls and the reviewer reports everything as missing."""
    cx, cy = (bbox_min[0] + bbox_max[0]) / 2.0, (bbox_min[1] + bbox_max[1]) / 2.0
    span_x, span_y = max(bbox_max[0] - bbox_min[0], 1e-6), max(bbox_max[1] - bbox_min[1], 1e-6)
    scene_area = span_x * span_y
    ground = bbox_min[2]
    dx, dy = camera_location[0] - cx, camera_location[1] - cy
    dlen = math.hypot(dx, dy) or 1.0
    dx, dy = dx / dlen, dy / dlen
    hidden = set()
    walls = []
    for name, box in boxes.items():
        size = [box["max"][k] - box["min"][k] for k in range(3)]
        footprint = size[0] * size[1]
        if _COVER.search(name) or (size[2] < 0.6 and footprint > 0.35 * scene_area and box["min"][2] > ground + 2.0):
            hidden.add(name)                                  # a roof or ceiling
            continue
        tall, thin, long_ = size[2] >= 1.8, min(size[0], size[1]) <= 0.8, max(size[0], size[1]) >= 2.5
        if not (tall and thin and long_):
            continue
        # where the wall stands, as a share of the scene's half-size on each axis (-1 = one edge, +1 = the other)
        px = ((box["min"][0] + box["max"][0]) / 2.0 - cx) / (span_x / 2.0)
        py = ((box["min"][1] + box["max"][1]) / 2.0 - cy) / (span_y / 2.0)
        if px * dx + py * dy > 0.5:                           # on the camera's side, near the edge
            walls.append(name)
    hidden.update(walls)
    return hidden


ENVELOPE_SUFFIXES = ("_walls", "_glass", "_brick", "_doors", "_metal")


def building_cutaways(names) -> Dict[str, list]:
    """mesh.building output in the scene -> {prefix: [its outer-wall objects]}: the parts to hide in a cutaway
    render so the rooms, halls and furniture inside can be seen."""
    names = set(names)
    found = {}
    for name in names:
        for marker in ("_rooms", "_furniture_wood"):
            if name.endswith(marker):
                prefix = name[: -len(marker)]
                envelope = [prefix + s for s in ENVELOPE_SUFFIXES if prefix + s in names]
                if prefix + "_walls" in names:
                    found[prefix] = envelope
    return found


def cutaway_pose(bbox_min: Sequence[float], bbox_max: Sequence[float]) -> Dict[str, list]:
    """A close front view of one building's lower floors (its outer walls are hidden for this render)."""
    sx, sy, sz = (bbox_max[k] - bbox_min[k] for k in range(3))
    cx = (bbox_min[0] + bbox_max[0]) / 2.0
    target = [cx, bbox_min[1] + 0.12 * sy, bbox_min[2] + 0.35 * sz]
    reach = max(0.45 * sx, 1.2 * sz, 8.0)
    location = [cx - 0.12 * sx, bbox_min[1] - reach, bbox_min[2] + 0.55 * sz]
    return {"location": location, "target": target}


def framing_box(boxes: Dict[str, dict], lo: Sequence[float], hi: Sequence[float]):
    """The box the check cameras frame: everything except big flat ground / floor planes, so a 140 m lawn does
    not shrink the buildings on it to a few pixels. Falls back to the whole scene."""
    total = max((hi[0] - lo[0]) * (hi[1] - lo[1]), 1e-6)
    keep = []
    for box in boxes.values():
        size = [box["max"][k] - box["min"][k] for k in range(3)]
        if size[2] < 0.35 and size[0] * size[1] > 0.3 * total:
            continue                                          # ground, lawn, terrain, big floor slab
        keep.append(box)
    if not keep:
        return list(lo), list(hi)
    flo = [min(b["min"][k] for b in keep) for k in range(3)]
    fhi = [max(b["max"][k] for b in keep) for k in range(3)]
    return flo, fhi
