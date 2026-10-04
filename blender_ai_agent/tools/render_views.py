"""
render_views.py
================
Hinglish: Banayi hui cheez ko kai angle (front, right, top, 3/4...) se dekhne ke liye camera ki jagah (pure maths, bpy nahi).
Bridge.render_views isse camera lagata hai. Dooriyan aisi ki poori cheez frame mein aaye (bounding sphere + margin).
"""

import math
from typing import Dict, Sequence

# Blender ka "Front" view: camera -Y par, +Y ki taraf dekhta hai; "Right": +X par; "Top": upar se.
VIEW_DIRECTIONS = {
    "front": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0), "right": (1.0, 0.0, 0.0), "left": (-1.0, 0.0, 0.0),
    "top": (0.0, -0.0005, 1.0), "bottom": (0.0, -0.0005, -1.0),
    "three_quarter": (1.0, -1.0, 0.65), "three_quarter_back": (-1.0, 1.0, 0.65),
}
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
    """Camera ki location + target (bounding box ka centre). Poori bounding sphere frame mein."""
    direction = VIEW_DIRECTIONS[normalize_view(view)]
    length = math.sqrt(sum(c * c for c in direction))
    unit = [c / length for c in direction]
    centre = [(bbox_min[k] + bbox_max[k]) / 2 for k in range(3)]
    radius = 0.5 * math.sqrt(sum((bbox_max[k] - bbox_min[k]) ** 2 for k in range(3)))
    radius = max(radius, 0.05)
    distance = radius * margin / math.sin(math.radians(fov_degrees) / 2)
    return {"location": [centre[k] + unit[k] * distance for k in range(3)], "target": centre, "distance": distance}