"""
character_builder.py
=====================
Hinglish: Cartoon character (chehra + badan) ka BUILDER. Pure Python (bpy nahi) — isliye poora test hota hai.
`build_character_spec(params)` ek "library model spec" deta hai (materials + parts), jise library_tools.place_model seedha
Blender mein laga deta hai. Kuch bhi hard-coded mesh nahi: sab kuch SDF (smooth blobs), UV-sphere aur curves se banta hai.

Character +Y ki taraf dekhta hai; tool use 180 degree ghuma deta hai taaki wo Blender ke "Front view" (Numpad 1) ki taraf dekhe.
Saari chehre ki cheezein head radius R ke hisaab se hain, isliye chibi (bada sir) aur normal (asli anupaat) dono style mein
aankhein-naak-munh sahi jagah par aate hain.
"""

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .mesh_generators import _shape_extent, lathe, sdf_mesh

Vec = Tuple[float, float, float]

STYLES = ("chibi", "normal")
GENDERS = ("neutral", "boy", "girl")
HAIR_STYLES = ("none", "short", "spiky", "bob", "long", "ponytail", "afro")
EXPRESSIONS = ("happy", "laugh", "sad", "angry", "surprised", "sleepy", "wink", "neutral")
OUTFITS = ("tshirt", "dress")
ACCESSORIES = ("glasses", "sunglasses", "cap", "beanie")
QUALITY_CELL = {"draft": 0.050, "low": 0.020, "medium": 0.014, "high": 0.010}

COLORS: Dict[str, List[float]] = {
    # skin
    "peach": [0.95, 0.70, 0.58], "light": [0.97, 0.80, 0.70], "fair": [0.96, 0.76, 0.65], "tan": [0.80, 0.55, 0.38],
    "brown": [0.45, 0.28, 0.17], "dark": [0.30, 0.18, 0.11], "olive": [0.72, 0.58, 0.38],
    # hair / general
    "black": [0.03, 0.03, 0.04], "blonde": [0.92, 0.75, 0.30], "yellow": [0.95, 0.85, 0.15], "ginger": [0.70, 0.25, 0.08],
    "red": [0.80, 0.07, 0.07], "orange": [0.95, 0.45, 0.05], "white": [0.95, 0.95, 0.95], "grey": [0.5, 0.5, 0.52],
    "gray": [0.5, 0.5, 0.52], "silver": [0.75, 0.76, 0.8], "blue": [0.12, 0.30, 0.85], "navy": [0.05, 0.08, 0.30],
    "green": [0.10, 0.60, 0.20], "teal": [0.05, 0.55, 0.55], "purple": [0.50, 0.15, 0.80], "pink": [0.95, 0.40, 0.65],
    "cyan": [0.1, 0.8, 0.9], "gold": [0.9, 0.7, 0.1],
}

# =============================================================================
# Maths / mesh helpers
# =============================================================================
def uv_sphere(segments: int = 16, rings: int = 10) -> Tuple[List[Vec], List[List[int]]]:
    """Unit UV-sphere (scale se ellipsoid ban jaata hai)."""
    profile = [(math.sin(math.pi * k / rings), -math.cos(math.pi * k / rings)) for k in range(rings + 1)]
    return lathe(profile, segments, 360.0, 0.0)


def _sdf_part(shapes: Sequence[Dict[str, Any]], cell: float, margin: float = 0.0):
    """Shapes ka mesh; resolution aise ki voxel ~`cell` metre ka ho (chhota part = kam voxel)."""
    lo, hi = [1e9] * 3, [-1e9] * 3
    for s in shapes:
        if str(s.get("op", "union")).lower() == "subtract" and s is not shapes[0]:
            continue
        e = _shape_extent(s) + float(s.get("k", 0.0)) * 0.5
        c = [float(v) for v in s.get("center", [0, 0, 0])]
        if str(s.get("type", "")).lower() == "capsule" and "center" not in s:
            c = [0.0, 0.0, 0.0]
        for k in range(3):
            lo[k], hi[k] = min(lo[k], c[k] - e), max(hi[k], c[k] + e)
    longest = max(hi[i] - lo[i] for i in range(3)) + 2 * margin
    for attempt in range(3):                                                  # bahut patla part khaali na nikle: baarik voxel se dobara
        step = cell / (1.6 ** attempt)
        resolution = int(max(10, min(80, round(longest / step))))
        vertices, faces = sdf_mesh(list(shapes), resolution, margin=max(margin, step * 1.5))
        if faces:
            return vertices, faces
    return vertices, faces


def _part_mesh(name, vertices, faces, material, smooth=True, offset=(0, 0, 0), scale=(1, 1, 1), rotation=(0, 0, 0)):
    return {"name": name, "kind": "mesh_data", "vertices": [list(v) for v in vertices], "faces": [list(f) for f in faces],
            "offset": list(offset), "rotation": list(rotation), "scale": list(scale), "material": material, "smooth": smooth}


def _ball(name, center, radii, material, sphere):
    """UV sphere ko ellipsoid bana kar rakhta hai."""
    return _part_mesh(name, sphere[0], sphere[1], material, True, offset=center, scale=radii)


def _curve(name, points, thickness, material, closed=False, rotation=(0, 0, 0), offset=(0, 0, 0)):
    return {"name": name, "kind": "curve", "points": [list(p) for p in points], "curve_type": "BEZIER", "thickness": thickness,
            "closed": closed, "offset": list(offset), "rotation": list(rotation), "material": material}


# =============================================================================
# Style tables
# =============================================================================
STYLE_TABLE = {
    "chibi": dict(head_r=0.25, head_z=0.75, torso=((0.17, 0.12, 0.19), 0.42), leg_x=0.085, leg_z=(0.08, 0.30), leg_r=0.055,
                  arm=((0.19, 0.0, 0.50), (0.27, 0.04, 0.34)), arm_r=0.042, hand_r=0.05, shoe=((0.07, 0.11, 0.05), 0.05)),
    "normal": dict(head_r=0.105, head_z=0.90, torso=((0.105, 0.065, 0.17), 0.66), leg_x=0.05, leg_z=(0.07, 0.52), leg_r=0.04,
                   arm=((0.12, 0.0, 0.78), (0.155, 0.02, 0.52)), arm_r=0.03, hand_r=0.03, shoe=((0.04, 0.075, 0.035), 0.035)),
}


def face_y(R: float, x: float, dz: float) -> float:
    """Head ellipsoid ki satah ka y (aage ki taraf) — chehre ki cheezein isi par chipakti hain."""
    t = 1.0 - (dz / (0.98 * R)) ** 2 - (x / R) ** 2
    return 0.94 * R * math.sqrt(max(0.05, t))


# =============================================================================
# Face
# =============================================================================
def _brow_points(R, hz, sign, expression):
    base_dz = 0.06 * R + 0.44 * R
    inner_x, outer_x = 0.16 * R, 0.58 * R
    inner, mid, outer = base_dz, base_dz + 0.04 * R, base_dz
    lift = 0.0
    if expression == "angry":
        inner, mid, outer = base_dz - 0.15 * R, base_dz - 0.04 * R, base_dz + 0.07 * R
    elif expression == "sad":
        inner, mid, outer = base_dz + 0.13 * R, base_dz + 0.05 * R, base_dz - 0.08 * R
    elif expression == "surprised":
        lift = 0.20 * R
    elif expression == "sleepy":
        lift = -0.10 * R
    elif expression == "laugh":
        lift = 0.06 * R
    xs = (sign * inner_x, sign * (inner_x + outer_x) / 2, sign * outer_x)
    dzs = (inner + lift, mid + lift, outer + lift)
    return [(x, face_y(R, x, dz) + 0.03 * R, hz + dz) for x, dz in zip(xs, dzs)]


def _mouth_parts(R, hz, expression, sphere) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    t = 0.045 * R

    def line(name, f, x0, x1, n=5, closed=False):
        xs = [x0 + (x1 - x0) * k / (n - 1) for k in range(n)]
        pts = [(x, face_y(R, x, f(x)) + 0.02 * R, hz + f(x)) for x in xs]
        return _curve(name, pts, t, "mouth", closed)

    if expression in ("happy", "wink"):
        parts.append(line("mouth", lambda x: -0.50 * R + 0.16 * R * (x / (0.32 * R)) ** 2, -0.32 * R, 0.32 * R))
    elif expression == "laugh":
        parts.append(_ball("mouth_open", (0, face_y(R, 0, -0.46 * R) - 0.06 * R, hz - 0.46 * R), (0.30 * R, 0.07 * R, 0.17 * R),
                           "mouth_inside", sphere))
        parts.append(line("mouth", lambda x: -0.36 * R + 0.10 * R * (x / (0.32 * R)) ** 2, -0.32 * R, 0.32 * R))
    elif expression == "sad":
        parts.append(line("mouth", lambda x: -0.40 * R - 0.14 * R * (x / (0.28 * R)) ** 2, -0.28 * R, 0.28 * R))
    elif expression == "angry":
        parts.append(line("mouth", lambda x: -0.46 * R - 0.06 * R * (x / (0.24 * R)) ** 2, -0.24 * R, 0.24 * R))
    elif expression == "surprised":
        cx, cz = 0.0, -0.46 * R
        ring = [(0.085 * R * math.cos(a), face_y(R, 0.085 * R * math.cos(a), cz + 0.115 * R * math.sin(a)) + 0.02 * R,
                 hz + cz + 0.115 * R * math.sin(a)) for a in [2 * math.pi * k / 8 for k in range(8)]]
        parts.append(_ball("mouth_open", (0, face_y(R, 0, cz) - 0.05 * R, hz + cz), (0.085 * R, 0.05 * R, 0.115 * R), "mouth_inside", sphere))
        parts.append(_curve("mouth", ring, t, "mouth", closed=True))
    elif expression == "sleepy":
        parts.append(line("mouth", lambda x: -0.46 * R, -0.12 * R, 0.12 * R, n=3))
    else:  # neutral
        parts.append(line("mouth", lambda x: -0.46 * R, -0.2 * R, 0.2 * R, n=3))
    return parts


def _eye_parts(R, hz, expression, gender, sphere) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    width, height = {"surprised": (1.12, 1.30), "sleepy": (1.0, 0.22), "laugh": (1.0, 0.80)}.get(expression, (1.0, 1.0))
    for side, sign in (("l", 1), ("r", -1)):
        ex, edz = sign * 0.36 * R, 0.06 * R
        if expression == "wink" and side == "r":
            pts = [(ex + sign * -0.20 * R * -1, 0, 0)]  # placeholder, neeche overwrite
            xs = [ex - 0.20 * R, ex, ex + 0.20 * R]
            dzs = [edz - 0.02 * R, edz - 0.10 * R, edz - 0.02 * R]
            arc = [(x, face_y(R, x, dz) + 0.025 * R, hz + dz) for x, dz in zip(xs, dzs)]
            parts.append(_curve("eye_r_closed", arc, 0.05 * R, "brow"))
            continue
        y_white = face_y(R, ex, edz) - 0.07 * R
        parts.append(_ball(f"eye_{side}_white", (ex, y_white, hz + edz), (0.22 * R * width, 0.12 * R, 0.26 * R * height), "eye_white", sphere))
        parts.append(_ball(f"eye_{side}_iris", (ex, y_white + 0.075 * R, hz + edz), (0.15 * R * min(width, 1.1), 0.06 * R, 0.19 * R * height), "iris", sphere))
        parts.append(_ball(f"eye_{side}_pupil", (ex, y_white + 0.105 * R, hz + edz), (0.085 * R * min(width, 1.1), 0.04 * R, 0.11 * R * height), "pupil", sphere))
        parts.append(_ball(f"eye_{side}_shine", (ex + 0.05 * R * sign * -1, y_white + 0.14 * R, hz + edz + 0.06 * R * height),
                           (0.035 * R, 0.02 * R, 0.035 * R), "eye_white", sphere))
        if gender == "girl" and expression not in ("sleepy",):
            lash = [(ex - sign * -0.0 + sign * 0.20 * R, face_y(R, ex + sign * 0.2 * R, edz + 0.22 * R * height) + 0.03 * R, hz + edz + 0.20 * R * height),
                    (ex + sign * 0.33 * R, face_y(R, ex + sign * 0.33 * R, edz + 0.28 * R * height) + 0.03 * R, hz + edz + 0.30 * R * height)]
            parts.append(_curve(f"lash_{side}", lash, 0.035 * R, "pupil"))
    return parts


def _hair_shapes(style, R, hz) -> List[Dict[str, Any]]:
    """Hair ke SDF shapes (head center (0,0,hz))."""
    def ell(radii, center, **kw):
        return dict({"type": "ellipsoid", "radii": [r * R for r in radii], "center": [center[0] * R, center[1] * R, hz + center[2] * R]}, **kw)

    def cut(size, center):
        return {"type": "box", "size": [s * R for s in size], "center": [center[0] * R, center[1] * R, hz + center[2] * R], "op": "subtract"}

    front_cut = cut((4.6, 2.2, 1.6), (0, 1.55, 0.50 - 0.80))                  # fringe ke neeche chehra khula
    if style == "short":
        return [ell((1.07, 1.03, 1.05), (0, -0.03, 0.03)), front_cut, cut((5, 5, 1.6), (0, 0, 0.10 - 0.80))]
    if style == "spiky":
        shapes = [ell((1.07, 1.03, 1.05), (0, -0.03, 0.03)), front_cut, cut((5, 5, 1.6), (0, 0, 0.10 - 0.80))]
        spikes = []
        for k in range(7):
            az = 2 * math.pi * k / 7
            tilt = 38
            pos = (0.88 * math.sin(math.radians(tilt)) * math.cos(az), 0.88 * math.sin(math.radians(tilt)) * math.sin(az) - 0.03,
                   0.88 * math.cos(math.radians(tilt)) + 0.03)
            spikes.append({"type": "cone", "radius": 0.30 * R, "radius_top": 0.0, "height": 0.62 * R,
                           "center": [pos[0] * R, pos[1] * R, hz + pos[2] * R], "rotation": [tilt, 0, math.degrees(az) + 90],
                           "op": "smooth_union", "k": 0.08 * R})
        spikes.append({"type": "cone", "radius": 0.30 * R, "height": 0.7 * R, "center": [0, -0.03 * R, hz + 0.95 * R],
                       "op": "smooth_union", "k": 0.08 * R})
        return shapes[:1] + spikes + shapes[1:]
    if style == "bob":
        return [ell((1.13, 1.09, 1.12), (0, -0.06, 0.02)), cut((4.6, 2.2, 1.8), (0, 1.5, 0.45 - 0.9)), cut((5, 5, 1.0), (0, 0, -0.78 - 0.5))]
    if style == "long":
        return [ell((1.13, 1.09, 1.12), (0, -0.06, 0.02)),
                ell((0.98, 0.55, 1.95), (0, -0.55, -1.00), op="smooth_union", k=0.25 * R),
                cut((4.6, 2.2, 1.8), (0, 1.5, 0.45 - 0.9)), cut((5, 5, 1.0), (0, 0, -2.6))]
    if style == "ponytail":
        return [ell((1.07, 1.03, 1.05), (0, -0.03, 0.03)),
                {"type": "capsule", "a": [0, -0.95 * R, hz + 0.40 * R], "b": [0, -1.55 * R, hz - 0.30 * R], "radius": 0.24 * R,
                 "op": "smooth_union", "k": 0.2 * R},
                front_cut, cut((5, 5, 1.6), (0, 0, 0.10 - 0.80))]
    if style == "afro":
        return [ell((1.38, 1.32, 1.32), (0, -0.10, 0.22)), cut((4.6, 2.2, 1.8), (0, 1.6, 0.52 - 0.9)), cut((6, 6, 1.5), (0, 0, -0.62 - 0.75))]
    return []


def _accessory_parts(accessory, R, hz, cell, sphere) -> List[Dict[str, Any]]:
    parts: List[Dict[str, Any]] = []
    if accessory in ("glasses", "sunglasses"):
        for side, sign in (("l", 1), ("r", -1)):
            cx, cdz = sign * 0.36 * R, 0.06 * R
            cy = face_y(R, cx, cdz) + 0.02 * R
            if accessory == "glasses":
                parts.append(_curve(f"glasses_{side}", [(0.30 * R * math.cos(a), 0, 0.30 * R * math.sin(a)) for a in [2 * math.pi * k / 10 for k in range(10)]],
                                    0.03 * R, "frame", closed=True, offset=(cx, cy, hz + cdz), rotation=(0, 0, 0)))
            else:
                parts.append(_ball(f"sunglasses_{side}", (cx, cy, hz + cdz), (0.34 * R, 0.05 * R, 0.27 * R), "lens", sphere))
            parts.append(_curve(f"temple_{side}", [(sign * 0.62 * R, cy - 0.01 * R, hz + cdz + 0.02 * R), (sign * 0.90 * R, cy * 0.35, hz + cdz + 0.04 * R),
                                                   (sign * 0.98 * R, -0.05 * R, hz + cdz)], 0.025 * R, "frame"))
        parts.append(_curve("glasses_bridge", [(-0.10 * R, face_y(R, 0, 0.08 * R) + 0.04 * R, hz + 0.10 * R),
                                                (0, face_y(R, 0, 0.1 * R) + 0.05 * R, hz + 0.12 * R),
                                                (0.10 * R, face_y(R, 0, 0.08 * R) + 0.04 * R, hz + 0.10 * R)], 0.03 * R, "frame"))
    elif accessory == "cap":
        shapes = [{"type": "ellipsoid", "radii": [1.10 * R, 1.08 * R, 1.10 * R], "center": [0, -0.03 * R, hz + 0.08 * R]},
                  {"type": "box", "size": [5 * R, 5 * R, 3 * R], "center": [0, 0, hz + 0.30 * R - 1.5 * R], "op": "subtract"},
                  {"type": "ellipsoid", "radii": [0.80 * R, 0.95 * R, 0.08 * R], "center": [0, 0.92 * R, hz + 0.33 * R], "op": "smooth_union", "k": 0.15 * R}]
        v, f = _sdf_part(shapes, cell)
        parts.append(_part_mesh("cap", v, f, "accessory"))
    elif accessory == "beanie":
        shapes = [{"type": "ellipsoid", "radii": [1.13 * R, 1.10 * R, 1.13 * R], "center": [0, -0.02 * R, hz + 0.05 * R]},
                  {"type": "box", "size": [5 * R, 5 * R, 3 * R], "center": [0, 0, hz + 0.28 * R - 1.5 * R], "op": "subtract"},
                  {"type": "sphere", "radius": 0.24 * R, "center": [0, 0, hz + 1.22 * R], "op": "smooth_union", "k": 0.1 * R}]
        v, f = _sdf_part(shapes, cell)
        parts.append(_part_mesh("beanie", v, f, "accessory"))
    return parts


# =============================================================================
# Whole character
# =============================================================================
def default_params() -> Dict[str, Any]:
    return {"style": "chibi", "gender": "neutral", "skin": "peach", "hair_style": None, "hair_color": "brown", "eye_color": "brown",
            "expression": "happy", "outfit": "tshirt", "shirt_color": None, "pants_color": None, "shoe_color": "brown",
            "accessories": [], "accessory_color": "red", "bust_only": False, "quality": "medium"}


def resolve_color(value: Any) -> List[float]:
    if isinstance(value, str) and value.strip().lower() in COLORS:
        return list(COLORS[value.strip().lower()])
    if isinstance(value, (list, tuple)) and len(value) in (3, 4):
        return [float(c) for c in value[:3]]
    raise ValueError(f"unknown colour {value!r}; use a name like {', '.join(sorted(COLORS)[:12])}... or [r, g, b]")


def build_character_spec(raw: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(default_params(), **{k: v for k, v in raw.items() if v is not None})
    style, gender, expression = p["style"], p["gender"], p["expression"]
    for value, allowed, label in ((style, STYLES, "style"), (gender, GENDERS, "gender"), (expression, EXPRESSIONS, "expression"),
                                  (p["outfit"], OUTFITS, "outfit")):
        if value not in allowed:
            raise ValueError(f"{label} must be one of {list(allowed)}, got '{value}'")
    hair_style = p["hair_style"] or {"girl": "long", "boy": "short", "neutral": "short"}[gender]
    if hair_style not in HAIR_STYLES:
        raise ValueError(f"hair_style must be one of {list(HAIR_STYLES)}, got '{hair_style}'")
    accessories = [a for a in p["accessories"]]
    for a in accessories:
        if a not in ACCESSORIES:
            raise ValueError(f"accessory must be one of {list(ACCESSORIES)}, got '{a}'")
    cell = QUALITY_CELL.get(p["quality"])
    if cell is None:
        raise ValueError(f"quality must be one of {list(QUALITY_CELL)}")

    S = STYLE_TABLE[style]
    R, hz = S["head_r"], S["head_z"]
    cell = cell * (R / 0.25) ** 0.5                                            # chhote (normal) style mein thoda bareek voxel
    shirt = p["shirt_color"] or {"boy": "blue", "girl": "pink", "neutral": "green"}[gender]
    pants = p["pants_color"] or ("navy" if p["outfit"] == "tshirt" else shirt)

    materials = {
        "skin": {"color": resolve_color(p["skin"])}, "hair": {"color": resolve_color(p["hair_color"])},
        "eye_white": {"color": [0.97, 0.97, 0.98]}, "iris": {"color": resolve_color(p["eye_color"])}, "pupil": {"color": [0.02, 0.02, 0.03]},
        "brow": {"color": [c * 0.5 for c in resolve_color(p["hair_color"])]}, "mouth": {"color": [0.45, 0.07, 0.08]},
        "mouth_inside": {"color": [0.30, 0.03, 0.05]}, "blush": {"color": [1.0, 0.50, 0.52]},
        "shirt": {"color": resolve_color(shirt)}, "pants": {"color": resolve_color(pants)}, "shoes": {"color": resolve_color(p["shoe_color"])},
        "accessory": {"color": resolve_color(p["accessory_color"])}, "frame": {"color": [0.05, 0.05, 0.06]},
        "lens": {"color": [0.02, 0.02, 0.03]},
    }
    sphere = uv_sphere(20, 12)
    parts: List[Dict[str, Any]] = []

    # ---- head ----
    head_shapes = [
        {"type": "ellipsoid", "radii": [R, 0.94 * R, 0.98 * R], "center": [0, 0, hz]},
        {"type": "sphere", "radius": 0.20 * R, "center": [0.97 * R, -0.02 * R, hz - 0.02 * R], "op": "smooth_union", "k": 0.08 * R},
        {"type": "sphere", "radius": 0.20 * R, "center": [-0.97 * R, -0.02 * R, hz - 0.02 * R], "op": "smooth_union", "k": 0.08 * R},
        {"type": "sphere", "radius": 0.14 * R, "center": [0, 0.90 * R, hz - 0.14 * R], "op": "smooth_union", "k": 0.10 * R},
        {"type": "ellipsoid", "radii": [0.55 * R, 0.55 * R, 0.42 * R], "center": [0, 0.22 * R, hz - 0.72 * R], "op": "smooth_union", "k": 0.30 * R},
    ]
    v, f = _sdf_part(head_shapes, cell)
    parts.append(_part_mesh("head", v, f, "skin"))

    # ---- face ----
    parts += _eye_parts(R, hz, expression, gender, sphere)
    for side, sign in (("l", 1), ("r", -1)):
        parts.append(_curve(f"brow_{side}", _brow_points(R, hz, sign, expression), 0.05 * R, "brow"))
    parts += _mouth_parts(R, hz, expression, sphere)
    if expression in ("happy", "laugh", "wink") or gender == "girl":
        for side, sign in (("l", 1), ("r", -1)):
            x, dz = sign * 0.64 * R, -0.18 * R
            parts.append(_ball(f"blush_{side}", (x, face_y(R, x, dz) - 0.015 * R, hz + dz), (0.16 * R, 0.03 * R, 0.10 * R), "blush", sphere))

    # ---- hair ----
    if hair_style != "none":
        v, f = _sdf_part(_hair_shapes(hair_style, R, hz), cell)
        parts.append(_part_mesh("hair", v, f, "hair"))

    # ---- accessories ----
    for accessory in accessories:
        parts += _accessory_parts(accessory, R, hz, cell, sphere)

    # ---- body ----
    (trx, try_, trz), tz = S["torso"]
    torso = [{"type": "ellipsoid", "radii": [trx, try_, trz], "center": [0, 0, tz]}]
    if p["outfit"] == "dress" and not p["bust_only"]:
        leg_span = S["leg_z"][1] - S["leg_z"][0]
        skirt_h = leg_span * 0.62                                           # ghutne tak; neeche pair aur joote dikhte hain
        torso.append({"type": "cone", "radius": trx * 1.38, "radius_top": trx * 0.80, "height": skirt_h,
                      "center": [0, 0, S["leg_z"][1] - skirt_h + 0.02], "op": "smooth_union", "k": 0.05})
    if p["bust_only"]:
        torso.append({"type": "box", "size": [1, 1, 1], "center": [0, 0, tz - trz * 0.55 - 0.5], "op": "subtract"})
    v, f = _sdf_part(torso, cell)
    parts.append(_part_mesh("torso", v, f, "shirt"))

    if not p["bust_only"]:
        (sx, sy, sz), (hx, hy, hz2) = S["arm"]
        for side, sign in (("l", 1), ("r", -1)):
            shapes = [{"type": "capsule", "a": [sign * sx, sy, sz], "b": [sign * hx, hy, hz2], "radius": S["arm_r"]}]
            v, f = _sdf_part(shapes, cell)
            parts.append(_part_mesh(f"arm_{side}", v, f, "shirt"))
            parts.append(_ball(f"hand_{side}", (sign * hx, hy, hz2 - 0.01), (S["hand_r"],) * 3, "skin", sphere))
        for side, sign in (("l", 1), ("r", -1)):
            z0, z1 = S["leg_z"]
            shapes = [{"type": "capsule", "a": [sign * S["leg_x"], 0, z0 + S["leg_r"]], "b": [sign * S["leg_x"], 0, z1], "radius": S["leg_r"]}]
            v, f = _sdf_part(shapes, cell)
            parts.append(_part_mesh(f"leg_{side}", v, f, "skin" if p["outfit"] == "dress" else "pants"))
            radii, shoe_z = S["shoe"]
            parts.append(_ball(f"shoe_{side}", (sign * S["leg_x"], radii[1] * 0.35, shoe_z), radii, "shoes", sphere))

    size = [2 * (trx * 1.6), 2 * R, hz + R] if not p["bust_only"] else [2 * R, 2 * R, 2 * R + trz]
    return {
        "category": "character", "size": size, "aliases": ["character", "cartoon character"],
        "description": f"{style} cartoon {gender} character, {expression} face, {hair_style} hair",
        "materials": materials, "parts": parts, "lights": [],
        "meta": {"style": style, "gender": gender, "expression": expression, "hair_style": hair_style, "accessories": accessories,
                 "head_radius": R, "head_z": hz},
    }