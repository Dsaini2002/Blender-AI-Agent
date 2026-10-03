"""
mesh_engine.py
===============
Hinglish: Mesh ko KUCH BHI banane ka general engine. Pure Python (bpy nahi), isliye poora test hota hai.

Soch: har "style" (pighla hua, mudaa hua, toota, kaante wala...) ke liye alag code likhne ke bajay chhote BLOCKS:

   1. SELECTION  — mesh ka kaun sa hissa (top, sphere, noise patch, up-facing, ...) -> har vertex ka weight 0..1
   2. OPERATORS  — move, scale, rotate, twist, bend, taper, stretch, bulge, inflate, noise, wave, melt, spikes, smooth,
                   crack, holes, erode, damage  (vertex move / face hatana)
                   subdivide, cut, extrude, shatter       (topology badalte hain)
   3. PRESETS    — common shabd ("melted", "twisted", "eroded"...) = in operators ki ek ready list
   4. PIPELINE   — operators ki list ek ke baad ek chalti hai: apply_ops()

Agent in blocks ko jodkar koi bhi request pooori kar sakta hai; jo block mein na ho uske liye mesh_script.py hai.

Sab kuch deterministic hai (same seed = same result). Coordinates WORLD space mein hain; "relative" ka matlab
object ke bounding box ke hisaab se 0..1 (0 = sabse neeche/left/front, 1 = sabse upar/right/back).
"""

import math
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .mesh_damage import plan_damage, region_vertex_indices, _REGION_AXIS
from .mesh_noise import fbm, rand01, ridged, value_noise

Vec = Tuple[float, float, float]
AXES = {"x": 0, "y": 1, "z": 2}

MAX_FACES = 150_000          # isse zyada faces wala result nahi banate (Blender / memory)
MAX_VERTICES = 200_000


# =============================================================================
# Maths helpers
# =============================================================================
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if x < lo else hi if x > hi else x


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge1 == edge0:
        return 1.0 if x >= edge1 else 0.0
    t = clamp((x - edge0) / (edge1 - edge0))
    return t * t * (3 - 2 * t)


def _sub(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(a: Sequence[float], s: float) -> Vec:
    return (a[0] * s, a[1] * s, a[2] * s)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Sequence[float], b: Sequence[float]) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _length(a: Sequence[float]) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _normalize(a: Sequence[float]) -> Vec:
    length = _length(a)
    return (a[0] / length, a[1] / length, a[2] / length) if length > 1e-12 else (0.0, 0.0, 1.0)


def _rotate_about_axis(p: Sequence[float], axis_index: int, angle: float, pivot: Sequence[float]) -> Vec:
    """p ko `pivot` ke through guzarti world axis ke gird angle (radian) ghumata hai."""
    c, s = math.cos(angle), math.sin(angle)
    q = [p[0] - pivot[0], p[1] - pivot[1], p[2] - pivot[2]]
    a, b = [i for i in range(3) if i != axis_index]
    qa, qb = q[a], q[b]
    q[a], q[b] = qa * c - qb * s, qa * s + qb * c
    return (q[0] + pivot[0], q[1] + pivot[1], q[2] + pivot[2])


# =============================================================================
# Mesh analysis
# =============================================================================
@dataclass
class MeshInfo:
    vertices: List[Vec]
    faces: List[List[int]]
    mins: List[float]
    maxs: List[float]
    center: List[float]
    extent: List[float]
    size: float
    normals: List[Vec]
    _adjacency: Optional[List[List[int]]] = field(default=None, repr=False)

    def rel(self, relative: Sequence[float]) -> Vec:
        """Bounding-box ke relative (0..1) point ko world coordinate mein."""
        return tuple(self.mins[i] + relative[i] * self.extent[i] for i in range(3))

    def adjacency(self) -> List[List[int]]:
        if self._adjacency is None:
            neighbours: List[set] = [set() for _ in self.vertices]
            for face in self.faces:
                count = len(face)
                for k in range(count):
                    a, b = face[k], face[(k + 1) % count]
                    neighbours[a].add(b)
                    neighbours[b].add(a)
            self._adjacency = [sorted(s) for s in neighbours]
        return self._adjacency

    def face_centroid(self, face: Sequence[int]) -> Vec:
        n = len(face)
        return (sum(self.vertices[i][0] for i in face) / n,
                sum(self.vertices[i][1] for i in face) / n,
                sum(self.vertices[i][2] for i in face) / n)


def vertex_normals(vertices: Sequence[Vec], faces: Sequence[Sequence[int]]) -> List[Vec]:
    normals = [[0.0, 0.0, 0.0] for _ in vertices]
    for face in faces:
        if len(face) < 3:
            continue
        nx = ny = nz = 0.0
        for k in range(len(face)):                         # Newell: area-weighted normal
            a, b = vertices[face[k]], vertices[face[(k + 1) % len(face)]]
            nx += (a[1] - b[1]) * (a[2] + b[2])
            ny += (a[2] - b[2]) * (a[0] + b[0])
            nz += (a[0] - b[0]) * (a[1] + b[1])
        for index in face:
            normals[index][0] += nx
            normals[index][1] += ny
            normals[index][2] += nz
    return [_normalize(n) for n in normals]


def analyze(vertices: Sequence[Vec], faces: Sequence[Sequence[int]]) -> MeshInfo:
    verts = [tuple(v) for v in vertices]
    if verts:
        mins = [min(v[i] for v in verts) for i in range(3)]
        maxs = [max(v[i] for v in verts) for i in range(3)]
    else:
        mins, maxs = [0.0] * 3, [0.0] * 3
    extent = [maxs[i] - mins[i] for i in range(3)]
    center = [(mins[i] + maxs[i]) / 2 for i in range(3)]
    size = max(max(extent), 1e-6)
    return MeshInfo(verts, [list(f) for f in faces], mins, maxs, center, extent, size,
                    vertex_normals(verts, faces))


# =============================================================================
# 1. SELECTION  ->  weight per vertex (0..1)
# =============================================================================
def falloff(depth: float, mode: str = "smooth") -> float:
    """depth: 0 = seema ke bahar/kinara, 1 = poora andar."""
    d = clamp(depth)
    if mode == "none":
        return 1.0 if depth > 1e-9 else 0.0
    if mode == "linear":
        return d
    if mode == "sharp":
        return d ** 3
    return d * d * (3 - 2 * d)                           # smooth (default)


REGION_ALIASES = {
    "upper": "top", "above": "top", "up": "top", "tip": "top", "neck": "top", "head": "top", "crown": "top", "lid": "top",
    "rim": "top", "mouth": "top", "opening": "top", "roof": "top", "cap": "top",
    "lower": "bottom", "base": "bottom", "down": "bottom", "foot": "bottom", "under": "bottom", "floor": "bottom",
    "right side": "right", "left side": "left", "whole": "all", "entire": "all", "everywhere": "all", "full": "all",
}

_FACING = {
    "up": (0, 0, 1), "down": (0, 0, -1), "left": (-1, 0, 0), "right": (1, 0, 0),
    "front": (0, -1, 0), "back": (0, 1, 0), "x": (1, 0, 0), "-x": (-1, 0, 0), "y": (0, 1, 0), "-y": (0, -1, 0),
    "z": (0, 0, 1), "-z": (0, 0, -1),
}


def _facing_weights(info: MeshInfo, direction: Any, threshold: float, mode: str) -> List[float]:
    vec = _FACING.get(direction) if isinstance(direction, str) else None
    if vec is None:
        vec = _normalize(direction) if isinstance(direction, (list, tuple)) and len(direction) == 3 else (0, 0, 1)
    threshold = clamp(threshold, 0.0, 0.99)
    return [falloff((_dot(n, vec) - threshold) / (1.0 - threshold), mode) if _dot(n, vec) > threshold else 0.0
            for n in info.normals]


def selection_weights(sel: Any, info: MeshInfo, seed: int = 1) -> List[float]:
    """
    `sel` kuch bhi ho sakta hai:
      None / "all"                          poora mesh
      "top" | "bottom" | "left" | "right" | "front" | "back"
      "up_facing" | "down_facing" | "sides"
      {"region": "top", "portion": 0.3}
      {"sphere": {"center": [0.5, 0.5, 1.0], "radius": 0.25}}      (center bbox-relative, radius object-size ka hissa)
      {"box": {"min": [0, 0, 0.6], "max": [1, 1, 1]}}              (bbox-relative)
      {"slab": {"axis": "z", "from": 0.4, "to": 0.6}}
      {"noise": {"scale": 3, "threshold": 0.5, "seed": 1}}         (patchy hissa)
      {"random": {"fraction": 0.2, "seed": 1}}
      {"facing": {"direction": "up", "tolerance": 0.5}}
      {"and": [sel, sel]}  {"or": [sel, sel]}  {"not": sel}
    Har dict mein optional: "falloff": smooth|linear|sharp|none, "invert": true, "strength": 0..1
    """
    n = len(info.vertices)
    if n == 0:
        return []
    if sel is None or sel is True or sel == "all":
        return [1.0] * n
    if isinstance(sel, str):
        if sel in ("up_facing", "down_facing", "sides"):
            sel = {"facing": {"direction": {"up_facing": "up", "down_facing": "down"}.get(sel, "up"),
                              "tolerance": 0.5}} if sel != "sides" else {"not": {"facing": {"direction": "up", "tolerance": 0.5}}}
            if isinstance(sel.get("not"), dict):
                sel = {"and": [{"not": {"facing": {"direction": "up", "tolerance": 0.5}}},
                               {"not": {"facing": {"direction": "down", "tolerance": 0.5}}}]}
        else:
            sel = {"region": REGION_ALIASES.get(sel.strip().lower().replace("_", " "), sel)}
    if not isinstance(sel, dict):
        raise ValueError(f"selection must be a name or an object, got {sel!r}")

    mode = sel.get("falloff", "smooth")
    rng_seed = int(sel.get("seed", seed))

    if "and" in sel:
        parts = [selection_weights(s, info, seed) for s in sel["and"]]
        weights = [1.0] * n
        for part in parts:
            weights = [a * b for a, b in zip(weights, part)]
    elif "or" in sel:
        parts = [selection_weights(s, info, seed) for s in sel["or"]]
        weights = [max(p[i] for p in parts) for i in range(n)] if parts else [0.0] * n
    elif "not" in sel:
        weights = [1.0 - w for w in selection_weights(sel["not"], info, seed)]
    elif "region" in sel:
        region = REGION_ALIASES.get(str(sel["region"]).strip().lower().replace("_", " "), sel["region"])
        if region == "all":
            weights = [1.0] * n
        elif region in ("up_facing", "down_facing"):
            weights = _facing_weights(info, "up" if region == "up_facing" else "down", 0.5, mode)
        elif region not in _REGION_AXIS:
            raise ValueError(f"unknown region '{region}'")
        else:
            depths = region_vertex_indices(info.vertices, region, float(sel.get("portion", 0.25)))
            weights = [falloff(depths[i], mode) if i in depths else 0.0 for i in range(n)]
    elif "sphere" in sel:
        spec = sel["sphere"] or {}
        centre = info.rel(spec.get("center", [0.5, 0.5, 0.5]))
        radius = max(1e-9, float(spec.get("radius", 0.25)) * info.size)
        weights = [falloff(1.0 - _length(_sub(v, centre)) / radius, mode) for v in info.vertices]
    elif "box" in sel:
        spec = sel["box"] or {}
        lo, hi = info.rel(spec.get("min", [0, 0, 0])), info.rel(spec.get("max", [1, 1, 1]))
        soft = float(spec.get("soft", 0.0)) * info.size
        weights = []
        for v in info.vertices:
            inside = min(min(v[i] - lo[i], hi[i] - v[i]) for i in range(3))
            weights.append(1.0 if inside >= 0 and soft <= 0 else clamp(inside / soft) if soft > 0 and inside >= 0 else 0.0)
    elif "slab" in sel:
        spec = sel["slab"] or {}
        axis = AXES.get(str(spec.get("axis", "z")), 2)
        a = info.mins[axis] + float(spec.get("from", 0.0)) * info.extent[axis]
        b = info.mins[axis] + float(spec.get("to", 1.0)) * info.extent[axis]
        soft = float(spec.get("soft", 0.0)) * info.size
        weights = []
        for v in info.vertices:
            inside = min(v[axis] - a, b - v[axis])
            weights.append(1.0 if inside >= 0 and soft <= 0 else clamp(inside / soft) if soft > 0 and inside >= 0 else 0.0)
    elif "noise" in sel:
        spec = sel["noise"] or {}
        scale = float(spec.get("scale", 3.0)) / info.size
        threshold = float(spec.get("threshold", 0.5))
        soft = max(1e-3, float(spec.get("soft", 0.1)))
        s = int(spec.get("seed", rng_seed))
        weights = [smoothstep(threshold - soft, threshold + soft,
                              0.5 + 0.5 * fbm(v[0] * scale, v[1] * scale, v[2] * scale, 3, seed=s)) for v in info.vertices]
    elif "random" in sel:
        spec = sel["random"] or {}
        fraction = clamp(float(spec.get("fraction", 0.2)))
        s = int(spec.get("seed", rng_seed))
        weights = [1.0 if rand01(i, s) < fraction else 0.0 for i in range(n)]
    elif "facing" in sel:
        spec = sel["facing"] or {}
        weights = _facing_weights(info, spec.get("direction", "up"), float(spec.get("tolerance", 0.5)), mode)
    elif sel.get("all"):
        weights = [1.0] * n
    else:
        raise ValueError(f"unknown selection {list(sel)}; use region/sphere/box/slab/noise/random/facing/and/or/not")

    if sel.get("invert"):
        weights = [1.0 - w for w in weights]
    strength = sel.get("strength")
    if strength is not None:
        weights = [w * clamp(float(strength)) for w in weights]
    return weights


# =============================================================================
# Operator plumbing
# =============================================================================
@dataclass
class OpResult:
    moves: Dict[int, Vec] = field(default_factory=dict)
    remove_faces: List[int] = field(default_factory=list)
    note: str = ""
    affected: int = 0


def _num(op: Dict[str, Any], key: str, default: float, lo: float = -1e9, hi: float = 1e9) -> float:
    try:
        value = float(op.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(lo, min(hi, value))


def _axis(op: Dict[str, Any], key: str = "axis", default: str = "z") -> int:
    return AXES.get(str(op.get(key, default)).strip().lower().lstrip("+"), AXES[default])


def _vec3(value: Any, default: Sequence[float]) -> List[float]:
    if isinstance(value, (int, float)):
        return [float(value)] * 3
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return [float(c) for c in value]
    return [float(c) for c in default]


def _pivot(spec: Any, info: MeshInfo, weights: Sequence[float]) -> Vec:
    if spec in (None, "center"):
        return tuple(info.center)
    if spec == "base":
        return (info.center[0], info.center[1], info.mins[2])
    if spec == "top":
        return (info.center[0], info.center[1], info.maxs[2])
    if spec == "selection":
        total = sum(weights)
        if total <= 1e-9:
            return tuple(info.center)
        return tuple(sum(info.vertices[i][k] * weights[i] for i in range(len(weights))) / total for k in range(3))
    if isinstance(spec, (list, tuple)) and len(spec) == 3:
        return info.rel(spec)
    return tuple(info.center)


def _blend(info: MeshInfo, weights: Sequence[float], fn) -> Dict[int, Vec]:
    """Har vertex ka naya position fn(i, p) se, weight ke hisaab se milakar."""
    moves: Dict[int, Vec] = {}
    for i, p in enumerate(info.vertices):
        w = weights[i]
        if w <= 1e-6:
            continue
        q = fn(i, p)
        if q is None:
            continue
        if w < 1.0:
            q = (p[0] + (q[0] - p[0]) * w, p[1] + (q[1] - p[1]) * w, p[2] + (q[2] - p[2]) * w)
        if q != p and any(abs(q[k] - p[k]) > 1e-12 for k in range(3)):
            moves[i] = (q[0], q[1], q[2])
    return moves


def _t_along(info: MeshInfo, axis: int, value: float) -> float:
    span = info.extent[axis]
    return (value - info.mins[axis]) / span if span > 1e-9 else 0.5


# =============================================================================
# 2. OPERATORS — vertex moves
# =============================================================================
def op_move(op, info, w, rng):
    absolute = bool(op.get("absolute", False))
    offset = _vec3(op.get("offset", [0, 0, 0]), [0, 0, 0])
    factor = 1.0 if absolute else info.size
    d = (offset[0] * factor, offset[1] * factor, offset[2] * factor)
    return OpResult(_blend(info, w, lambda i, p: (p[0] + d[0], p[1] + d[1], p[2] + d[2])))


def op_scale(op, info, w, rng):
    factor = _vec3(op.get("factor", 1.0), [1, 1, 1])
    pivot = _pivot(op.get("pivot"), info, w)
    return OpResult(_blend(info, w, lambda i, p: tuple(pivot[k] + (p[k] - pivot[k]) * factor[k] for k in range(3))))


def op_rotate(op, info, w, rng):
    axis, angle = _axis(op), math.radians(_num(op, "angle", 0.0))
    pivot = _pivot(op.get("pivot"), info, w)
    return OpResult(_blend(info, w, lambda i, p: _rotate_about_axis(p, axis, angle, pivot)))


def op_twist(op, info, w, rng):
    axis, total = _axis(op), math.radians(_num(op, "angle", 90.0))
    centered = bool(op.get("centered", True))
    pivot = tuple(info.center)

    def fn(i, p):
        t = _t_along(info, axis, p[axis])
        return _rotate_about_axis(p, axis, total * ((t - 0.5) if centered else t), pivot)

    return OpResult(_blend(info, w, fn))


def op_bend(op, info, w, rng):
    """Mesh ko lambai (axis) ke saath mod deta hai. `direction` = kis taraf jhukega."""
    axis = _axis(op, "axis", "z")
    direction = _axis(op, "direction", "x" if axis != 0 else "y")
    if direction == axis:
        direction = [k for k in range(3) if k != axis][0]
    angle = math.radians(_num(op, "angle", 45.0))
    if abs(angle) < 1e-9:
        return OpResult()
    length = max(info.extent[axis], 1e-9)
    radius = length / angle
    a0 = info.mins[axis] if op.get("pivot", "base") == "base" else info.center[axis]
    d0 = info.center[direction]

    def fn(i, p):
        phi = (p[axis] - a0) / radius
        r = radius - (p[direction] - d0)
        q = list(p)
        q[axis] = a0 + r * math.sin(phi)
        q[direction] = d0 + radius - r * math.cos(phi)
        return tuple(q)

    return OpResult(_blend(info, w, fn))


def op_taper(op, info, w, rng):
    axis = _axis(op)
    start, end = _num(op, "start", 1.0, 0.0, 10.0), _num(op, "end", 0.3, 0.0, 10.0)
    perp = [k for k in range(3) if k != axis]

    def fn(i, p):
        t = _t_along(info, axis, p[axis])
        s = start + (end - start) * t
        q = list(p)
        for k in perp:
            q[k] = info.center[k] + (p[k] - info.center[k]) * s
        return tuple(q)

    return OpResult(_blend(info, w, fn))


def op_stretch(op, info, w, rng):
    axis, factor = _axis(op), _num(op, "factor", 1.5, 0.01, 20.0)
    pivot = _pivot(op.get("pivot", "center"), info, w)
    keep = bool(op.get("preserve_volume", False))
    side = 1.0 / math.sqrt(factor) if keep else 1.0
    perp = [k for k in range(3) if k != axis]

    def fn(i, p):
        q = list(p)
        q[axis] = pivot[axis] + (p[axis] - pivot[axis]) * factor
        if keep:
            for k in perp:
                q[k] = pivot[k] + (p[k] - pivot[k]) * side
        return tuple(q)

    return OpResult(_blend(info, w, fn))


def op_bulge(op, info, w, rng):
    axis, amount = _axis(op), _num(op, "amount", 0.3, -0.95, 5.0)
    shape = op.get("shape", "belly")
    perp = [k for k in range(3) if k != axis]

    def fn(i, p):
        t = _t_along(info, axis, p[axis])
        bell = math.sin(math.pi * clamp(t)) if shape == "belly" else 1.0 - math.sin(math.pi * clamp(t))
        s = 1.0 + amount * bell
        q = list(p)
        for k in perp:
            q[k] = info.center[k] + (p[k] - info.center[k]) * s
        return tuple(q)

    return OpResult(_blend(info, w, fn))


def op_inflate(op, info, w, rng):
    amount = _num(op, "amount", 0.05, -0.5, 0.5) * info.size
    return OpResult(_blend(info, w, lambda i, p: _add(p, _scale(info.normals[i], amount))))


def op_noise(op, info, w, rng):
    amplitude = _num(op, "amplitude", 0.03, 0.0, 1.0) * info.size
    frequency = _num(op, "scale", 4.0, 0.1, 200.0) / info.size
    octaves = int(_num(op, "octaves", 3, 1, 6))
    seed = int(_num(op, "seed", 1, 0, 10 ** 6))
    mode = str(op.get("mode", "normal")).lower()
    use_ridged = bool(op.get("ridged", False))

    def sample(x, y, z, offset=0):
        if use_ridged:
            return ridged(x * frequency, y * frequency, z * frequency, octaves, seed + offset)
        return fbm(x * frequency, y * frequency, z * frequency, octaves, seed=seed + offset)

    def fn(i, p):
        if mode == "xyz":
            return (p[0] + sample(*p, 11) * amplitude, p[1] + sample(*p, 23) * amplitude, p[2] + sample(*p, 37) * amplitude)
        direction = info.normals[i] if mode == "normal" else tuple(1.0 if k == AXES.get(mode, 2) else 0.0 for k in range(3))
        return _add(p, _scale(direction, sample(*p) * amplitude))

    return OpResult(_blend(info, w, fn))


def op_wave(op, info, w, rng):
    amplitude = _num(op, "amplitude", 0.03, 0.0, 1.0) * info.size
    wavelength = max(1e-4, _num(op, "wavelength", 0.25, 0.01, 10.0)) * info.size
    travel = _axis(op, "axis", "x")
    phase = math.radians(_num(op, "phase", 0.0))
    displace = str(op.get("displace", "normal")).lower()

    def fn(i, p):
        height = amplitude * math.sin(2 * math.pi * (p[travel] - info.mins[travel]) / wavelength + phase)
        direction = info.normals[i] if displace == "normal" else tuple(1.0 if k == AXES.get(displace, 2) else 0.0 for k in range(3))
        return _add(p, _scale(direction, height))

    return OpResult(_blend(info, w, fn))


def op_melt(op, info, w, rng):
    """Upar ka hissa neeche tapakta hai aur neeche ki taraf phailta hai (puddle)."""
    amount, spread = _num(op, "amount", 0.4, 0.0, 1.0), _num(op, "spread", 0.5, 0.0, 3.0)
    seed = int(_num(op, "seed", 1, 0, 10 ** 6))
    lo = min((info.vertices[i][2] for i in range(len(w)) if w[i] > 1e-6), default=info.mins[2])
    hi = max((info.vertices[i][2] for i in range(len(w)) if w[i] > 1e-6), default=info.maxs[2])
    span = max(hi - lo, 1e-9)
    frequency = 3.0 / info.size

    def fn(i, p):
        t = (p[2] - lo) / span
        jitter = 0.65 + 0.7 * (0.5 + 0.5 * value_noise(p[0] * frequency, p[1] * frequency, 0.0, seed))
        drop = amount * span * (t ** 1.3) * jitter
        grow = 1.0 + spread * amount * (1.0 - t) ** 2
        return (info.center[0] + (p[0] - info.center[0]) * grow,
                info.center[1] + (p[1] - info.center[1]) * grow,
                max(info.mins[2], p[2] - drop))

    return OpResult(_blend(info, w, fn))


def op_spikes(op, info, w, rng):
    count = int(_num(op, "count", 12, 1, 400))
    length = _num(op, "length", 0.15, 0.0, 2.0) * info.size
    radius = max(1e-6, _num(op, "radius", 0.06, 0.005, 1.0) * info.size)
    candidates = [i for i in range(len(w)) if w[i] > 0.3]
    if not candidates:
        return OpResult()
    seeds = rng.sample(candidates, min(count, len(candidates)))
    pull = [0.0] * len(info.vertices)
    for s in seeds:
        centre = info.vertices[s]
        for i, v in enumerate(info.vertices):
            d = _length(_sub(v, centre)) / radius
            if d < 1.0:
                # nokdaar cone: (1-d)^2
                pull[i] = max(pull[i], (1.0 - d) ** 2) if i != s else 1.0
    moves = {}
    for i, amount in enumerate(pull):
        if amount > 1e-6 and w[i] > 1e-6:
            moves[i] = _add(info.vertices[i], _scale(info.normals[i], length * amount * w[i]))
    return OpResult(moves)


def op_smooth(op, info, w, rng):
    iterations = int(_num(op, "iterations", 2, 1, 30))
    factor = _num(op, "factor", 0.5, 0.0, 1.0)
    adjacency = info.adjacency()
    current = [list(v) for v in info.vertices]
    for _ in range(iterations):
        nxt = [list(v) for v in current]
        for i, neighbours in enumerate(adjacency):
            if w[i] <= 1e-6 or not neighbours:
                continue
            avg = [sum(current[n][k] for n in neighbours) / len(neighbours) for k in range(3)]
            blend = factor * w[i]
            for k in range(3):
                nxt[i][k] = current[i][k] + (avg[k] - current[i][k]) * blend
        current = nxt
    moves = {i: tuple(current[i]) for i in range(len(current))
             if w[i] > 1e-6 and any(abs(current[i][k] - info.vertices[i][k]) > 1e-12 for k in range(3))}
    return OpResult(moves)


def _segment_distance(p: Sequence[float], a: Sequence[float], b: Sequence[float]) -> float:
    ab = _sub(b, a)
    length_sq = _dot(ab, ab)
    t = 0.0 if length_sq < 1e-18 else clamp(_dot(_sub(p, a), ab) / length_sq)
    return _length(_sub(p, _add(a, _scale(ab, t))))


def op_crack(op, info, w, rng):
    """Satah par tedhi-medhi daraar (groove) banata hai, dono taraf se thoda khulti hui."""
    count = int(_num(op, "count", 3, 1, 20))
    depth = _num(op, "depth", 0.03, 0.0, 0.5) * info.size
    width = max(1e-6, _num(op, "width", 0.012, 0.001, 0.3) * info.size)
    length = _num(op, "length", 0.5, 0.05, 3.0) * info.size
    jagged = _num(op, "jaggedness", 0.6, 0.0, 1.0)
    candidates = [i for i in range(len(w)) if w[i] > 0.3]
    if not candidates:
        return OpResult()

    step = max(width * 2.0, length / 14.0)
    paths: List[List[Vec]] = []
    for _ in range(count):
        start = rng.choice(candidates)
        position = info.vertices[start]
        normal = info.normals[start]
        tangent = _cross(normal, (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        direction = _normalize(tangent)
        points = [position]
        for _ in range(max(2, int(length / step))):
            wobble = _cross(normal, direction)
            direction = _normalize(_add(direction, _scale(wobble, rng.uniform(-1, 1) * jagged)))
            position = _add(position, _scale(direction, step))
            points.append(position)
        paths.append(points)

    moves: Dict[int, Vec] = {}
    for i, v in enumerate(info.vertices):
        if w[i] <= 1e-6:
            continue
        best, side = None, None
        for points in paths:
            for a, b in zip(points, points[1:]):
                d = _segment_distance(v, a, b)
                if best is None or d < best:
                    best = d
                    side = _cross(_sub(b, a), info.normals[i])
        if best is None or best >= width:
            continue
        strength = (1.0 - best / width) ** 1.5 * w[i]
        push_in = _scale(info.normals[i], -depth * strength)
        open_up = _scale(_normalize(side), (depth * 0.4 * strength) * (1 if best < width * 0.5 else -1)) if side else (0, 0, 0)
        moves[i] = _add(_add(v, push_in), open_up)
    return OpResult(moves)


# =============================================================================
# 2b. OPERATORS — face removal
# =============================================================================
def _face_weight(face: Sequence[int], w: Sequence[float]) -> float:
    return sum(w[i] for i in face) / len(face) if face else 0.0


def op_holes(op, info, w, rng):
    """Gol-gol chhed (ya `fraction` ke hisaab se randomly faces gayab)."""
    candidates = [fi for fi, f in enumerate(info.faces) if _face_weight(f, w) > 0.5]
    if not candidates:
        return OpResult()
    if "fraction" in op:
        fraction = clamp(_num(op, "fraction", 0.1))
        chosen = [fi for fi in candidates if rng.random() < fraction]
        return OpResult(remove_faces=chosen, note=f"{len(chosen)} faces removed")
    count = int(_num(op, "count", 5, 1, 200))
    radius = _num(op, "radius", 0.06, 0.005, 1.0) * info.size
    centres = [info.face_centroid(info.faces[fi]) for fi in rng.sample(candidates, min(count, len(candidates)))]
    cand_set = set(candidates)
    removed = [fi for fi in cand_set
               if any(_length(_sub(info.face_centroid(info.faces[fi]), c)) <= radius for c in centres)]
    return OpResult(remove_faces=sorted(removed), note=f"{len(removed)} faces removed in {len(centres)} holes")


def op_erode(op, info, w, rng):
    """Noise ke hisaab se hissa khaa liya gaya (galta hua / zang laga) + kinaaron par halka khurdurapan."""
    threshold = _num(op, "threshold", 0.68, 0.3, 0.95)
    frequency = _num(op, "scale", 4.0, 0.5, 100.0) / info.size
    seed = int(_num(op, "seed", 1, 0, 10 ** 6))
    amount = _num(op, "amount", 0.01, 0.0, 0.2) * info.size
    removed = []
    for fi, f in enumerate(info.faces):
        if _face_weight(f, w) <= 0.3:
            continue
        c = info.face_centroid(f)
        if 0.5 + 0.5 * fbm(c[0] * frequency, c[1] * frequency, c[2] * frequency, 3, seed=seed) > threshold:
            removed.append(fi)
    moves = _blend(info, w, lambda i, p: _add(p, _scale(
        info.normals[i], fbm(p[0] * frequency * 3, p[1] * frequency * 3, p[2] * frequency * 3, 2, seed=seed + 5) * amount)))
    return OpResult(moves, removed, f"{len(removed)} faces eroded away")


def op_damage(op, info, w, rng):
    """Purana `mesh.damage` (broken / chipped / dented / rough) — engine ka hissa."""
    plan = plan_damage(info.vertices, info.faces, str(op.get("region", "top")), _num(op, "portion", 0.25, 0.02, 1.0),
                       _num(op, "strength", 0.15, 0.01, 0.6), str(op.get("style", "broken")),
                       int(_num(op, "seed", 1, 0, 10 ** 6)))
    moves = {i: p for i, p in plan.moves.items() if w[i] > 1e-6}
    return OpResult(moves, [f for f in plan.remove_faces if _face_weight(info.faces[f], w) > 1e-6],
                    affected=plan.affected)


VERTEX_OPS = {
    "move": op_move, "scale": op_scale, "rotate": op_rotate, "twist": op_twist, "bend": op_bend, "taper": op_taper,
    "stretch": op_stretch, "bulge": op_bulge, "inflate": op_inflate, "noise": op_noise, "wave": op_wave,
    "melt": op_melt, "spikes": op_spikes, "smooth": op_smooth, "crack": op_crack,
    "holes": op_holes, "erode": op_erode, "damage": op_damage,
}
TOPOLOGY_OPS = {"subdivide", "cut", "extrude", "shatter"}
ALL_OPS = set(VERTEX_OPS) | TOPOLOGY_OPS | {"script"}


def run_vertex_op(op: Dict[str, Any], info: MeshInfo, default_seed: int = 1) -> OpResult:
    """Ek (topology na badalne wala) operator chalata hai."""
    name = op.get("op")
    if name == "script":                                    # mesh_script.py (sandbox) — import yahan taaki circular na ho
        from .mesh_script import run_script
        return run_script(info, str(op.get("code", "")), op.get("select"), int(op.get("seed", default_seed)))
    if name not in VERTEX_OPS:
        raise ValueError(f"unknown operator '{name}'")
    seed = int(op.get("seed", default_seed))
    rng = random.Random(seed)
    weights = selection_weights(op.get("select"), info, seed)
    result = VERTEX_OPS[name](op, info, weights, rng)
    result.affected = result.affected or sum(1 for x in weights if x > 1e-6)
    return result


# =============================================================================
# 3. OPERATORS — topology (nayi geometry banate / hatate hain)
# =============================================================================
@dataclass
class TopologyResult:
    vertices: List[Vec]
    faces: List[List[int]]
    face_source: List[int]          # har naye face ka asli (input) face index; -1 = bilkul naya (cap jaisa)
    note: str = ""


def compact_mesh(vertices: Sequence[Vec], faces: Sequence[Sequence[int]]):
    """Jo vertices kisi face mein nahi hain unhe hata deta hai (indices dobara banata hai)."""
    used = sorted({i for f in faces for i in f})
    remap = {old: new for new, old in enumerate(used)}
    return [tuple(vertices[i]) for i in used], [[remap[i] for i in f] for f in faces]


def _face_normal(vertices: Sequence[Vec], face: Sequence[int]) -> Vec:
    nx = ny = nz = 0.0
    for k in range(len(face)):
        a, b = vertices[face[k]], vertices[face[(k + 1) % len(face)]]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return _normalize((nx, ny, nz))


def subdivide_mesh(vertices, faces, vertex_weights, levels=1, threshold=0.3):
    """
    Linear subdivision. Sirf wahi edges katte hain jinke dono vertices ka weight > threshold. Jo face poora
    chun liya gaya wo 4 hisson mein; jo adha chuna gaya wo n-gon banta hai (koi T-junction / daraar nahi).
    """
    verts = [tuple(v) for v in vertices]
    fcs = [list(f) for f in faces]
    weights = list(vertex_weights)
    source = list(range(len(fcs)))
    notes = []
    for _ in range(max(1, min(3, int(levels)))):
        original_count = len(verts)
        midpoint: Dict[Tuple[int, int], int] = {}

        def mid(a, b):
            key = (a, b) if a < b else (b, a)
            if key not in midpoint:
                va, vb = verts[a], verts[b]
                verts.append(((va[0] + vb[0]) / 2, (va[1] + vb[1]) / 2, (va[2] + vb[2]) / 2))
                weights.append((weights[a] + weights[b]) / 2)
                midpoint[key] = len(verts) - 1
            return midpoint[key]

        def selected(a, b):
            return a < original_count and b < original_count and weights[a] > threshold and weights[b] > threshold

        new_faces, new_source = [], []
        # pehle andaaza: bahut zyada faces na ban jaayein
        predicted = 0
        for f in fcs:
            flags = [selected(f[k], f[(k + 1) % len(f)]) for k in range(len(f))]
            predicted += len(f) if all(flags) else 1
        if predicted > MAX_FACES:
            notes.append(f"subdivide stopped: would exceed {MAX_FACES} faces")
            break
        for fi, f in enumerate(fcs):
            n = len(f)
            flags = [selected(f[k], f[(k + 1) % n]) for k in range(n)]
            if all(flags):
                centre = tuple(sum(verts[i][c] for i in f) / n for c in range(3))
                verts.append(centre)
                weights.append(sum(weights[i] for i in f) / n)
                ci = len(verts) - 1
                mids = [mid(f[k], f[(k + 1) % n]) for k in range(n)]
                for k in range(n):
                    new_faces.append([f[k], mids[k], ci, mids[k - 1]])
                    new_source.append(source[fi])
            elif any(flags):
                loop = []
                for k in range(n):
                    loop.append(f[k])
                    if flags[k]:
                        loop.append(mid(f[k], f[(k + 1) % n]))
                new_faces.append(loop)
                new_source.append(source[fi])
            else:
                new_faces.append(list(f))
                new_source.append(source[fi])
        fcs, source = new_faces, new_source
    return TopologyResult(verts, fcs, source, notes[0] if notes else f"subdivided to {len(fcs)} faces")


def cut_plane(vertices, faces, axis: int, value: float, keep: str = "below", cap: bool = True) -> TopologyResult:
    """
    Mesh ko ek (world-axis wale) plane se kaat deta hai (Sutherland-Hodgman, asli geometry cut). `keep`: below|above.
    cap=True par kati hui jagah ko dhak deta hai (andar khokhla nahi dikhta).
    """
    eps = 1e-9
    keep_below = keep != "above"
    base = len(vertices)

    def inside(v):
        d = v[axis] - value
        return d <= eps if keep_below else d >= -eps

    verts = [tuple(v) for v in vertices]
    cache: Dict[Tuple[int, int], int] = {}

    def intersect(a, b):
        key = (a, b) if a < b else (b, a)
        if key not in cache:
            va, vb = verts[a], verts[b]
            denom = vb[axis] - va[axis]
            t = 0.5 if abs(denom) < 1e-18 else (value - va[axis]) / denom
            p = [va[k] + (vb[k] - va[k]) * t for k in range(3)]
            p[axis] = value
            verts.append(tuple(p))
            cache[key] = len(verts) - 1
        return cache[key]

    new_faces, source, cut_edges = [], [], []
    for fi, f in enumerate(faces):
        flags = [inside(vertices[i]) for i in f]
        if all(flags):
            new_faces.append(list(f))
            source.append(fi)
            continue
        if not any(flags):
            continue
        out = []
        n = len(f)
        for k in range(n):
            a, b = f[k], f[(k + 1) % n]
            ia, ib = flags[k], flags[(k + 1) % n]
            if ia and ib:
                out.append(b)
            elif ia and not ib:
                out.append(intersect(a, b))
            elif not ia and ib:
                out.append(intersect(a, b))
                out.append(b)
        if len(out) >= 3:
            new_faces.append(out)
            source.append(fi)
            for k in range(len(out)):
                a, b = out[k], out[(k + 1) % len(out)]
                if a >= base and b >= base:
                    cut_edges.append((a, b))
    if not new_faces:
        raise ValueError("the cut would remove the whole mesh; choose a different position or side")

    cap_count = 0
    if cap and cut_edges:
        neighbours: Dict[int, List[int]] = {}
        for a, b in cut_edges:
            neighbours.setdefault(a, []).append(b)
            neighbours.setdefault(b, []).append(a)
        visited_edges = set()
        for a, b in cut_edges:
            if (min(a, b), max(a, b)) in visited_edges:
                continue
            loop, previous, current = [a], None, a
            while True:
                options = [x for x in neighbours[current] if (min(current, x), max(current, x)) not in visited_edges]
                if not options:
                    break
                nxt = options[0]
                visited_edges.add((min(current, nxt), max(current, nxt)))
                if nxt == loop[0]:
                    break
                loop.append(nxt)
                previous, current = current, nxt
            if len(loop) >= 3:
                normal = _face_normal(verts, loop)
                outward = (0, 0, 0)
                outward = tuple((1.0 if (k == axis and keep_below) else -1.0 if k == axis else 0.0) for k in range(3))
                if _dot(normal, outward) < 0:
                    loop.reverse()
                new_faces.append(loop)
                source.append(-1)
                cap_count += 1

    compact_v, compact_f = compact_mesh(verts, new_faces)
    return TopologyResult(compact_v, compact_f, source, f"cut at {'xyz'[axis]}={value:.4g}, kept {'below' if keep_below else 'above'}"
                          + (f", {cap_count} cap(s)" if cap_count else ""))


def extrude_faces(vertices, faces, face_ids, amount: float) -> TopologyResult:
    """Chune hue faces ko normal ki disha mein `amount` (world units) khinchta hai (side walls ke saath)."""
    verts = [tuple(v) for v in vertices]
    selected = set(face_ids)
    new_faces, source = [], []
    for fi, f in enumerate(faces):
        if fi not in selected:
            new_faces.append(list(f))
            source.append(fi)
            continue
        normal = _face_normal(vertices, f)
        top = []
        for i in f:
            verts.append(_add(vertices[i], _scale(normal, amount)))
            top.append(len(verts) - 1)
        new_faces.append(top)
        source.append(fi)
        for k in range(len(f)):
            new_faces.append([f[k], f[(k + 1) % len(f)], top[(k + 1) % len(f)], top[k]])
            source.append(fi)
    return TopologyResult(verts, new_faces, source, f"extruded {len(selected)} faces")


def shatter_mesh(info: MeshInfo, face_ids: Sequence[int], pieces: int, spread: float, rotate_degrees: float,
                 rng: random.Random) -> TopologyResult:
    """
    Chune hue faces ko `pieces` tukdon (Voronoi jaisa) mein baant ke har tukde ko thoda bahar/ghumaa deta hai.
    Tukde alag hote hain (vertices duplicate), isliye toota hua kaanch / bikhra hua dikhta hai.
    """
    ids = list(face_ids)
    if not ids:
        raise ValueError("shatter: nothing is selected")
    centroids = {fi: info.face_centroid(info.faces[fi]) for fi in ids}
    pieces = max(2, min(pieces, len(ids)))

    seeds = [rng.choice(ids)]                              # farthest-point sampling: seeds door-door
    while len(seeds) < pieces:
        best = max(ids, key=lambda fi: min(_length(_sub(centroids[fi], centroids[s])) for s in seeds))
        seeds.append(best)
    cluster = {fi: min(range(len(seeds)), key=lambda k: _length(_sub(centroids[fi], centroids[seeds[k]]))) for fi in ids}

    members: Dict[int, List[int]] = {}
    for fi, k in cluster.items():
        members.setdefault(k, []).append(fi)
    transforms = {}
    for k, fids in members.items():
        c = tuple(sum(centroids[fi][a] for fi in fids) / len(fids) for a in range(3))
        away = _sub(c, tuple(info.center))
        direction = _normalize(away) if _length(away) > 1e-9 else _normalize((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        offset = _scale(direction, spread * info.size * rng.uniform(0.6, 1.0))
        transforms[k] = (c, offset, rng.choice((0, 1, 2)), math.radians(rotate_degrees) * rng.uniform(-1, 1))

    verts: List[Vec] = []
    index: Dict[Tuple[int, int], int] = {}

    def vertex_for(v, k):
        key = (v, k)
        if key not in index:
            p = info.vertices[v]
            if k >= 0:
                c, offset, axis, angle = transforms[k]
                p = _rotate_about_axis(p, axis, angle, c)
                p = _add(p, offset)
            verts.append(tuple(p))
            index[key] = len(verts) - 1
        return index[key]

    new_faces, source = [], []
    for fi, f in enumerate(info.faces):
        k = cluster.get(fi, -1)
        new_faces.append([vertex_for(v, k) for v in f])
        source.append(fi)
    return TopologyResult(verts, new_faces, source, f"shattered into {len(members)} pieces")


def apply_topology(op: Dict[str, Any], vertices, faces, default_seed: int = 1) -> TopologyResult:
    name = op.get("op")
    info = analyze(vertices, faces)
    seed = int(op.get("seed", default_seed))
    rng = random.Random(seed)
    weights = selection_weights(op.get("select"), info, seed)

    if name == "subdivide":
        return subdivide_mesh(info.vertices, info.faces, weights, int(_num(op, "levels", 1, 1, 3)),
                              _num(op, "threshold", 0.3, 0.0, 0.99))
    if name == "cut":
        axis = _axis(op, "axis", "z")
        if "value" in op:
            value = _num(op, "value", info.center[axis])
        else:
            value = info.mins[axis] + _num(op, "at", 0.5, 0.0, 1.0) * info.extent[axis]
        return cut_plane(info.vertices, info.faces, axis, value, str(op.get("keep", "below")), bool(op.get("cap", True)))
    if name == "extrude":
        ids = [fi for fi, f in enumerate(info.faces) if _face_weight(f, weights) > 0.5]
        if not ids:
            raise ValueError("extrude: no faces are selected")
        return extrude_faces(info.vertices, info.faces, ids, _num(op, "amount", 0.05, -1.0, 1.0) * info.size)
    if name == "shatter":
        ids = [fi for fi, f in enumerate(info.faces) if _face_weight(f, weights) > 0.5]
        return shatter_mesh(info, ids, int(_num(op, "pieces", 10, 2, 200)), _num(op, "spread", 0.08, 0.0, 3.0),
                            _num(op, "rotate", 15.0, 0.0, 180.0), rng)
    raise ValueError(f"unknown topology operator '{name}'")


# =============================================================================
# 4. PRESETS — aam shabd = operators ki ready list
# =============================================================================
def _with(sel, ops):
    return [dict(o, select=o.get("select", sel)) if sel is not None else dict(o) for o in ops]


def _p_melted(s, sel, seed, region):
    return _with(sel, [{"op": "melt", "amount": 0.15 + 0.6 * s, "spread": 0.4 + 0.6 * s, "seed": seed},
                       {"op": "smooth", "iterations": 2, "factor": 0.4}])


PRESETS = {
    "melted": _p_melted,
    "twisted": lambda s, sel, seed, region: _with(sel, [{"op": "twist", "angle": 60 + 300 * s}]),
    "bent": lambda s, sel, seed, region: _with(sel, [{"op": "bend", "angle": 20 + 100 * s}]),
    "crushed": lambda s, sel, seed, region: _with(sel, [
        {"op": "stretch", "axis": "z", "factor": 1 - 0.55 * s, "preserve_volume": True, "pivot": "base"},
        {"op": "noise", "amplitude": 0.02 * s, "scale": 5, "seed": seed}]),
    "stretched": lambda s, sel, seed, region: _with(sel, [{"op": "stretch", "axis": "z", "factor": 1 + 1.5 * s, "pivot": "base"}]),
    "pointed": lambda s, sel, seed, region: _with(sel, [{"op": "taper", "axis": "z", "start": 1.0, "end": max(0.02, 1 - 0.95 * s)}]),
    "inflated": lambda s, sel, seed, region: _with(sel, [{"op": "inflate", "amount": 0.02 + 0.12 * s}, {"op": "smooth", "iterations": 2}]),
    "deflated": lambda s, sel, seed, region: _with(sel, [{"op": "inflate", "amount": -(0.02 + 0.1 * s)}, {"op": "smooth", "iterations": 1}]),
    "hammered": lambda s, sel, seed, region: _with(sel, [{"op": "noise", "amplitude": 0.008 + 0.03 * s, "scale": 14, "octaves": 2, "seed": seed}]),
    "bumpy": lambda s, sel, seed, region: _with(sel, [{"op": "noise", "amplitude": 0.02 + 0.08 * s, "scale": 3, "octaves": 3, "seed": seed}]),
    "rough": lambda s, sel, seed, region: _with(sel, [{"op": "noise", "amplitude": 0.004 + 0.02 * s, "scale": 10, "octaves": 4, "seed": seed}]),
    "wrinkled": lambda s, sel, seed, region: _with(sel, [{"op": "noise", "amplitude": 0.01 + 0.05 * s, "scale": 7, "octaves": 3, "ridged": True, "seed": seed}]),
    "crumpled": lambda s, sel, seed, region: _with(sel, [
        {"op": "noise", "amplitude": 0.04 + 0.12 * s, "scale": 4, "ridged": True, "seed": seed}, {"op": "bend", "angle": 15 * s}]),
    "eroded": lambda s, sel, seed, region: _with(sel, [
        {"op": "erode", "threshold": 0.8 - 0.3 * s, "scale": 4, "amount": 0.01 + 0.02 * s, "seed": seed}]),
    "aged": lambda s, sel, seed, region: _with(sel, [
        {"op": "noise", "amplitude": 0.004 + 0.015 * s, "scale": 9, "octaves": 4, "seed": seed},
        {"op": "erode", "threshold": 0.9 - 0.2 * s, "scale": 5, "amount": 0.004, "seed": seed + 3}]),
    "cracked": lambda s, sel, seed, region: _with(sel, [
        {"op": "crack", "count": 2 + int(6 * s), "depth": 0.02 + 0.06 * s, "width": 0.01 + 0.02 * s, "seed": seed}]),
    "broken": lambda s, sel, seed, region: [{"op": "damage", "style": "broken", "region": region, "strength": 0.05 + 0.4 * s, "seed": seed}],
    "chipped": lambda s, sel, seed, region: [{"op": "damage", "style": "chipped", "region": region, "strength": 0.05 + 0.4 * s, "seed": seed}],
    "dented": lambda s, sel, seed, region: [{"op": "damage", "style": "dented", "region": region, "strength": 0.05 + 0.3 * s, "seed": seed}],
    "spiky": lambda s, sel, seed, region: _with(sel, [{"op": "spikes", "count": 10 + int(40 * s), "length": 0.05 + 0.2 * s, "radius": 0.05, "seed": seed}]),
    "wavy": lambda s, sel, seed, region: _with(sel, [{"op": "wave", "amplitude": 0.01 + 0.06 * s, "wavelength": 0.3, "axis": "x"}]),
    "wobbly": lambda s, sel, seed, region: _with(sel, [
        {"op": "wave", "amplitude": 0.01 + 0.04 * s, "wavelength": 0.4, "axis": "z"}, {"op": "twist", "angle": 25 * s}]),
    "shattered": lambda s, sel, seed, region: _with(sel, [
        {"op": "shatter", "pieces": 6 + int(30 * s), "spread": 0.02 + 0.15 * s, "rotate": 8 + 25 * s, "seed": seed}]),
    "exploded": lambda s, sel, seed, region: _with(sel, [
        {"op": "shatter", "pieces": 12 + int(30 * s), "spread": 0.2 + 0.8 * s, "rotate": 40, "seed": seed}]),
    "holey": lambda s, sel, seed, region: _with(sel, [{"op": "holes", "count": 4 + int(12 * s), "radius": 0.04 + 0.05 * s, "seed": seed}]),
    "sliced": lambda s, sel, seed, region: [{"op": "cut", "axis": "z", "at": 0.5, "keep": "below", "cap": True}],
}

PRESET_ALIASES = {
    "melt": "melted", "melting": "melted", "droopy": "melted", "drooping": "melted", "dripping": "melted", "pighla": "melted",
    "pighla hua": "melted", "twist": "twisted", "twisting": "twisted", "spiral": "twisted", "ghumaya": "twisted",
    "bend": "bent", "curved": "bent", "mudaa": "bent", "muda hua": "bent", "crooked": "bent", "tedha": "bent",
    "crush": "crushed", "squashed": "crushed", "squash": "crushed", "flattened": "crushed", "pichka": "dented",
    "stretch": "stretched", "elongated": "stretched", "lamba": "stretched", "tall": "stretched",
    "pointy": "pointed", "tapered": "pointed", "taper": "pointed", "sharp": "pointed", "nukila": "pointed",
    "inflate": "inflated", "puffy": "inflated", "swollen": "inflated", "fat": "inflated", "balloon": "inflated",
    "shrunken": "deflated", "deflate": "deflated", "hammer": "hammered", "dimpled": "hammered", "pitted": "hammered",
    "lumpy": "bumpy", "bump": "bumpy", "uneven": "bumpy", "worn": "rough", "scratched": "rough", "khurdura": "rough",
    "weathered": "rough", "gritty": "rough", "wrinkle": "wrinkled", "creased": "wrinkled", "crinkled": "wrinkled",
    "crumple": "crumpled", "erode": "eroded", "corroded": "eroded", "rusty": "eroded", "decayed": "eroded", "rotten": "eroded",
    "old": "aged", "ancient": "aged", "antique": "aged", "crack": "cracked", "fractured": "cracked", "split": "cracked",
    "break": "broken", "shatter": "shattered", "smashed": "broken", "snapped": "broken", "damaged": "broken",
    "toota": "broken", "toota hua": "broken", "chip": "chipped", "dent": "dented", "spike": "spiky", "thorny": "spiky",
    "kaante wala": "spiky", "kaantedaar": "spiky", "wave": "wavy", "rippled": "wavy", "ripple": "wavy", "wobble": "wobbly",
    "explode": "exploded", "blown apart": "exploded", "holes": "holey", "perforated": "holey", "chhed": "holey",
    "chhedwala": "holey", "cut": "sliced", "cut in half": "sliced", "half": "sliced", "slice": "sliced", "sectioned": "sliced",
}
PRESET_NAMES = tuple(sorted(PRESETS))

_NEEDS_DETAIL = {"melted", "twisted", "bent", "pointed", "inflated", "deflated", "hammered", "bumpy", "rough", "wrinkled",
                 "crumpled", "eroded", "aged", "cracked", "spiky", "wavy", "wobbly", "crushed"}


def resolve_preset_name(name: str) -> Optional[str]:
    key = str(name or "").strip().lower().replace("_", " ").replace("-", " ")
    if key in PRESETS:
        return key
    return PRESET_ALIASES.get(key) or PRESET_ALIASES.get(key.replace(" ", ""))


def expand_preset(name: str, strength: float = 0.5, select: Any = None, seed: int = 1, detail: Optional[int] = None,
                  region: str = "top", face_count: int = 0) -> List[Dict[str, Any]]:
    """Preset ka naam (ya synonym) -> operators ki list. detail=None: kam polygon wale mesh par khud 1 subdivide jodta hai."""
    resolved = resolve_preset_name(name)
    if resolved is None:
        raise ValueError(f"unknown preset '{name}'. Presets: {', '.join(PRESET_NAMES)}")
    s = clamp(float(strength), 0.02, 1.0)
    ops = PRESETS[resolved](s, select, seed, region)
    if detail is None:
        detail = 1 if (resolved in _NEEDS_DETAIL and face_count < 4000) else 0
    if detail and resolved in _NEEDS_DETAIL:
        ops = [dict({"op": "subdivide", "levels": int(detail)}, **({"select": select} if select is not None else {}))] + ops
    return ops


# =============================================================================
# 4b. Parameter normalisation (LLM kai tarah ke formats bhejte hain)
# =============================================================================
_VECTOR_KEYS = {"offset", "factor", "center", "min", "max", "rotation", "size", "radii", "a", "b", "bounds", "pivot", "direction"}
_TEXT_KEYS = {"op", "name", "code", "region", "style", "axis", "mode", "keep", "shape", "falloff", "displace", "preset", "type"}


def _finite_float(text: Any) -> Optional[float]:
    try:
        value = float(str(text).strip())
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def normalize_params(value: Any, key: Optional[str] = None) -> Any:
    """
    Operator / shape ke parameters ko saaf form mein badalta hai:
      {"x": 1, "y": 2, "z": 3}  -> [1, 2, 3]       "1, 2, 3" (vector wali keys par) -> [1.0, 2.0, 3.0]
      "90" -> 90.0                                  ["0", "1"] -> [0.0, 1.0]
    Text wali keys (op, region, style, axis, code...) ko kabhi nahi chhedta.
    """
    if isinstance(value, dict):
        lowered = {str(k).lower(): v for k, v in value.items()}
        if set(lowered) == {"x", "y", "z"}:
            return [(_finite_float(lowered[c]) if _finite_float(lowered[c]) is not None else lowered[c]) for c in "xyz"]
        return {k: normalize_params(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [normalize_params(v, key) for v in value]
    if isinstance(value, str):
        if key in _TEXT_KEYS:
            return value
        if key in _VECTOR_KEYS:
            tokens = [t for t in value.strip().strip("[]()").replace(";", ",").replace(",", " ").split() if t]
            numbers = [_finite_float(t) for t in tokens]
            if 2 <= len(tokens) <= 6 and all(n is not None for n in numbers):
                return numbers
        number = _finite_float(value)
        return number if number is not None else value
    return value


# =============================================================================
# 5. PIPELINE
# =============================================================================
@dataclass
class MeshResult:
    vertices: List[Vec]
    faces: List[List[int]]
    face_source: List[int]
    notes: List[str]
    topology_changed: bool
    removed_faces: List[int]            # asli faces jo gayab hue (sirf tab bharosemand jab topology_changed False)


def apply_ops(vertices, faces, ops: Sequence[Dict[str, Any]], default_seed: int = 1) -> MeshResult:
    """Operators ki list ko ek ke baad ek chalata hai. Pure function — input ko nahi chhedta."""
    verts = [tuple(v) for v in vertices]
    fcs = [list(f) for f in faces]
    source = list(range(len(fcs)))
    notes: List[str] = []
    topology_changed = False

    queue = [normalize_params(dict(o)) for o in ops]
    while queue:
        op = queue.pop(0)
        name = op.get("op")
        if name == "preset":
            queue = expand_preset(op.get("name", ""), float(op.get("strength", 0.5)), op.get("select"),
                                  int(op.get("seed", default_seed)), op.get("detail"), str(op.get("region", "top")),
                                  len(fcs)) + queue
            continue
        if name in TOPOLOGY_OPS:
            result = apply_topology(op, verts, fcs, default_seed)
            verts, fcs = result.vertices, result.faces
            source = [source[s] if s >= 0 else -1 for s in result.face_source]
            topology_changed = True
            notes.append(f"{name}: {result.note}")
        else:
            info = analyze(verts, fcs)
            outcome = run_vertex_op(op, info, default_seed)
            for index, position in outcome.moves.items():
                verts[index] = position
            if outcome.remove_faces:
                gone = set(outcome.remove_faces)
                keep = [fi for fi in range(len(fcs)) if fi not in gone]
                fcs = [fcs[fi] for fi in keep]
                source = [source[fi] for fi in keep]
            notes.append(f"{name}: moved {len(outcome.moves)} vertices" + (f", {outcome.note}" if outcome.note else ""))
        if len(fcs) > MAX_FACES or len(verts) > MAX_VERTICES:
            raise ValueError(f"result too large ({len(fcs)} faces); use fewer subdivisions")

    surviving = {s for s in source if s >= 0}
    removed = [] if topology_changed else sorted(set(range(len(faces))) - surviving)
    return MeshResult(verts, fcs, source, notes, topology_changed, removed)


def validate_ops(ops: Sequence[Any]) -> List[Dict[str, Any]]:
    """Operators ki list ko jaanch ke saaf form mein deta hai (galat naam / selection par ValueError)."""
    if not isinstance(ops, (list, tuple)) or not ops:
        raise ValueError("ops must be a non-empty list of operators, e.g. [{\"op\": \"twist\", \"angle\": 90}]")
    if len(ops) > 40:
        raise ValueError("too many operators (max 40)")
    dummy = analyze([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
                    [[0, 1, 2, 3], [4, 5, 6, 7]])
    clean = []
    for number, op in enumerate(ops):
        if not isinstance(op, dict) or "op" not in op:
            raise ValueError(f"ops[{number}] must be an object with an 'op' key")
        name = op["op"]
        if name == "preset":
            resolved = resolve_preset_name(op.get("name", ""))
            if resolved is None:
                raise ValueError(f"ops[{number}]: unknown preset '{op.get('name')}'. Presets: {', '.join(PRESET_NAMES)}")
        elif name not in ALL_OPS:
            raise ValueError(f"ops[{number}]: unknown operator '{name}'. Operators: {', '.join(sorted(ALL_OPS))}, preset")
        if name == "script":
            from .mesh_script import compile_script
            try:
                compile_script(str(op.get("code", "")))
            except ValueError as exc:
                raise ValueError(f"ops[{number}] script: {exc}") from exc
        try:
            selection_weights(op.get("select"), dummy, 1)
        except ValueError as exc:
            raise ValueError(f"ops[{number}] select: {exc}") from exc
        clean.append(normalize_params(dict(op)))
    return clean