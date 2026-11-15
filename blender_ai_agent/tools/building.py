"""mesh.building: a complete multi-storey building in ONE call.

A model asked for "a G+5 hostel" used to scale three cubes - no floors, no windows, nothing inside. This tool
builds the real thing from a few numbers, so the result looks right whatever model writes the call:

  shape        rect | L | U | courtyard (closed ring)           blocks are `wing_depth` thick
  structure    floor slabs (visible bands), columns, roof slab, parapet, stair / lift headrooms, water tanks
  facades      a window per bay (frame, mullion, glass), balconies with railings, red-brick fins and plinth,
               brick end walls; on courtyard sides an open corridor (gallery) with railings and room doors
  entrance     glass front with double doors, a canopy on columns, steps and an optional sign (3D text)
  inside       floor plates, room partitions, a bed / study desk / chair / wardrobe / ceiling fan in every room,
               ground-floor halls (reception + security desk, mess with dining tables, recreation room with
               table-tennis tables, library with shelves, study room), stair flights and lift shafts

Local frame: the footprint is centred on `location`, the main front (entrance) faces -Y and, for L / U, the
wings run towards +Y with the courtyard between them (open at the back for a U). Meshes are merged per
material (one object each), so even 200 furnished rooms stay light.
"""

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .base import Permission, Tool, ToolResult
from .models import _coerce_bool, _coerce_list, _coerce_number, _vec3

Rect = Tuple[float, float, float, float]          # x0, x1, y0, y1 (local)

# bucket -> (object suffix, material name, recipe, params, collection role)
BUCKETS = {
    "frame": ("_structure", "bld_concrete", "concrete", {"color": [0.62, 0.61, 0.58, 1.0]}, "building"),
    "wall": ("_walls", "bld_white_wall", "paint", {"color": [0.86, 0.85, 0.82, 1.0], "roughness": 0.7}, "building"),
    "brick": ("_brick", "bld_brick", "brick", {}, "building"),
    "glass": ("_glass", "bld_glass", "glass", {"color": [0.75, 0.86, 0.92, 1.0], "roughness": 0.03}, "building"),
    "metal": ("_metal", "bld_metal", "metal_brushed", {"color": [0.2, 0.21, 0.23, 1.0], "roughness": 0.35}, "building"),
    "door": ("_doors", "bld_door_wood", "wood_grain", {"dark": [0.16, 0.08, 0.035, 1.0], "light": [0.36, 0.19, 0.08, 1.0]}, "building"),
    "stairs": ("_stairs", "bld_concrete", "concrete", {"color": [0.62, 0.61, 0.58, 1.0]}, "building"),
    "rooms": ("_rooms", "bld_partition", "paint", {"color": [0.93, 0.92, 0.88, 1.0], "roughness": 0.8}, "rooms"),
    "wood": ("_furniture_wood", "bld_furniture_wood", "wood_grain", {"dark": [0.25, 0.14, 0.07, 1.0], "light": [0.55, 0.36, 0.2, 1.0]}, "furniture"),
    "soft": ("_furniture_soft", "bld_fabric", "fabric", {"color": [0.2, 0.32, 0.55, 1.0]}, "furniture"),
    "fan": ("_ceiling_fans", "bld_fan", "paint", {"color": [0.92, 0.92, 0.9, 1.0], "roughness": 0.4}, "furniture"),
    "tt": ("_tt_tables", "bld_tt_top", "paint", {"color": [0.03, 0.18, 0.12, 1.0], "roughness": 0.4}, "furniture"),
    "lamp": ("_ceiling_lights", "bld_ceiling_light", "glow", {"color": [1.0, 0.95, 0.85, 1.0], "strength": 18.0}, "building"),
    "roof": ("_roof", "bld_roof", "concrete", {"color": [0.55, 0.54, 0.52, 1.0]}, "building"),
    "garden": ("_roof_garden", "bld_roof_garden", "foliage", {"color": [0.13, 0.4, 0.12, 1.0]}, "building"),
}
ROOF_STYLES = {"flat": "flat", "terrace": "terrace", "garden": "terrace", "roof_garden": "terrace", "green": "terrace",
               "gable": "gable", "pitched": "gable", "sloped": "gable", "slanted": "gable", "a_frame": "gable",
               "triangle": "gable", "triangular": "gable", "hip": "hip", "hipped": "hip", "pyramid": "hip",
               "tiled": "hip", "tile": "hip", "sloping": "gable"}
PITCHED_ROOF_COLOR = [0.5, 0.17, 0.1, 1.0]            # terracotta tiles
WALL_T = 0.25


class Mesher:
    """Collects boxes per bucket; boxes are 8 corners so they can sit in any (rotated) frame."""

    def __init__(self):
        self.boxes: Dict[str, List[List[Tuple[float, float, float]]]] = {k: [] for k in BUCKETS}

    def box(self, key, x0, x1, y0, y1, z0, z1):
        if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
            return
        self.boxes[key].append([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])

    def rbox(self, key, cx, cy, z0, z1, hx, hy, yaw):
        c, s = math.cos(yaw), math.sin(yaw)
        ring = [(cx + c * dx - s * dy, cy + s * dx + c * dy) for dx, dy in ((-hx, -hy), (hx, -hy), (hx, hy), (-hx, hy))]
        self.boxes[key].append([(x, y, z0) for x, y in ring] + [(x, y, z1) for x, y in ring])

    def mesh(self, key):
        verts, faces = [], []
        for corners in self.boxes[key]:
            b = len(verts)
            verts += [tuple(round(c, 4) for c in p) for p in corners]
            faces += [(b, b + 3, b + 2, b + 1), (b + 4, b + 5, b + 6, b + 7), (b, b + 1, b + 5, b + 4),
                      (b + 1, b + 2, b + 6, b + 5), (b + 2, b + 3, b + 7, b + 6), (b + 3, b, b + 4, b + 7)]
        return verts, faces

    def count(self):
        return sum(len(v) for v in self.boxes.values())


class Frame:
    """A face of the building: u runs along the face (0..length), v points OUT of the building, z is height.
    The mapping is a proper rotation, so boxes keep outward normals."""

    def __init__(self, m: Mesher, origin, n):
        self.m, self.ox, self.oy, self.nx, self.ny = m, origin[0], origin[1], n[0], n[1]
        self.ux, self.uy = n[1], -n[0]

    def pt(self, u, v):
        return self.ox + self.ux * u + self.nx * v, self.oy + self.uy * u + self.ny * v

    def box(self, key, u0, u1, v0, v1, z0, z1):
        if u1 - u0 < 1e-4 or v1 - v0 < 1e-4 or z1 - z0 < 1e-4:
            return
        ring = [self.pt(u0, v0), self.pt(u1, v0), self.pt(u1, v1), self.pt(u0, v1)]
        self.m.boxes[key].append([(x, y, z0) for x, y in ring] + [(x, y, z1) for x, y in ring])


# ------------------------------------------------------------------ layout
def blocks_for(shape: str, w: float, d: float, wd: float) -> Tuple[List[Rect], Optional[Rect]]:
    hx, hy = w / 2.0, d / 2.0
    if shape == "rect":
        return [(-hx, hx, -hy, hy)], None
    base = (-hx, hx, -hy, -hy + wd)
    left = (-hx, -hx + wd, -hy + wd, hy)
    if shape == "l":
        return [base, left], (-hx + wd, hx, -hy + wd, hy)
    right = (hx - wd, hx, -hy + wd, hy)
    if shape == "u":
        return [base, left, right], (-hx + wd, hx - wd, -hy + wd, hy)
    back = (-hx + wd, hx - wd, hy - wd, hy)
    return [base, left, right, back], (-hx + wd, hx - wd, -hy + wd, hy - wd)


def _subtract(intervals, cut):
    a, b = cut
    out = []
    for s, e in intervals:
        if b <= s + 1e-6 or a >= e - 1e-6:
            out.append((s, e))
            continue
        if a > s + 1e-6:
            out.append((s, a))
        if b < e - 1e-6:
            out.append((b, e))
    return out


def exposed_faces(blocks: List[Rect], blockers: List[Rect]):
    """(block index, side, line coord, normal, [(a, b) intervals along the face]) for every outside face."""
    faces = []
    for i, (x0, x1, y0, y1) in enumerate(blocks):
        sides = (("front", y0, (0.0, -1.0), (x0, x1)), ("back", y1, (0.0, 1.0), (x0, x1)),
                 ("left", x0, (-1.0, 0.0), (y0, y1)), ("right", x1, (1.0, 0.0), (y0, y1)))
        for side, line, n, span in sides:
            intervals = [span]
            for j, other in enumerate(blocks + blockers):
                if j == i:
                    continue
                ox0, ox1, oy0, oy1 = other
                if n[1] != 0:                                    # face along X at y = line
                    touches = (oy0 - 1e-6 <= line <= oy1 + 1e-6) and (oy1 - oy0 > 1e-6)
                    if touches and ((n[1] < 0 and oy0 < line - 1e-6) or (n[1] > 0 and oy1 > line + 1e-6)
                                    or j >= len(blocks)):
                        intervals = _subtract(intervals, (ox0, ox1))
                else:
                    touches = (ox0 - 1e-6 <= line <= ox1 + 1e-6) and (ox1 - ox0 > 1e-6)
                    if touches and ((n[0] < 0 and ox0 < line - 1e-6) or (n[0] > 0 and ox1 > line + 1e-6)
                                    or j >= len(blocks)):
                        intervals = _subtract(intervals, (oy0, oy1))
            intervals = [(a, b) for a, b in intervals if b - a > 0.5]
            if intervals:
                faces.append((i, side, line, n, intervals))
    return faces


def _inside(rect: Optional[Rect], x, y) -> bool:
    return rect is not None and rect[0] < x < rect[1] and rect[2] < y < rect[3]


# ------------------------------------------------------------------ furniture (local xy, z = floor top)
def bed(m, x0, y0, along_x, z):
    """Single bed 0.95 x 2.0 starting at (x0, y0) going +X (along_x) or +Y."""
    w, l = 0.95, 2.0
    x1, y1 = (x0 + l, y0 + w) if along_x else (x0 + w, y0 + l)
    m.box("wood", x0, x1, y0, y1, z + 0.08, z + 0.35)
    for lx, ly in ((x0, y0), (x1 - 0.06, y0), (x0, y1 - 0.06), (x1 - 0.06, y1 - 0.06)):
        m.box("wood", lx, lx + 0.06, ly, ly + 0.06, z, z + 0.08)
    m.box("soft", x0 + 0.03, x1 - 0.03, y0 + 0.03, y1 - 0.03, z + 0.35, z + 0.52)
    if along_x:
        m.box("wood", x0 - 0.05, x0, y0, y1, z, z + 0.95)
        m.box("soft", x0 + 0.08, x0 + 0.5, y0 + 0.12, y1 - 0.12, z + 0.52, z + 0.62)
    else:
        m.box("wood", x0, x1, y0 - 0.05, y0, z, z + 0.95)
        m.box("soft", x0 + 0.12, x1 - 0.12, y0 + 0.08, y0 + 0.5, z + 0.52, z + 0.62)


def table(m, cx, cy, z, sx, sy, height=0.75, key="wood"):
    m.box(key, cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, z + height - 0.04, z + height)
    for dx in (-1, 1):
        for dy in (-1, 1):
            lx, ly = cx + dx * (sx / 2 - 0.06), cy + dy * (sy / 2 - 0.06)
            m.box("wood", lx - 0.03, lx + 0.03, ly - 0.03, ly + 0.03, z, z + height - 0.04)


def chair(m, cx, cy, z, back_dir):
    """Chair with its back towards back_dir: one of (1,0), (-1,0), (0,1), (0,-1)."""
    h = 0.22
    m.box("wood", cx - h, cx + h, cy - h, cy + h, z + 0.43, z + 0.47)
    for dx in (-1, 1):
        for dy in (-1, 1):
            lx, ly = cx + dx * (h - 0.03), cy + dy * (h - 0.03)
            m.box("wood", lx - 0.02, lx + 0.02, ly - 0.02, ly + 0.02, z, z + 0.43)
    bx, by = back_dir
    if bx:
        x = cx + bx * (h - 0.02)
        m.box("wood", x - 0.02, x + 0.02, cy - h, cy + h, z + 0.47, z + 0.92)
    else:
        y = cy + by * (h - 0.02)
        m.box("wood", cx - h, cx + h, y - 0.02, y + 0.02, z + 0.47, z + 0.92)


def bench(m, cx, cy, z, sx, sy):
    m.box("wood", cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, z + 0.42, z + 0.46)
    for end in (-1, 1):
        if sx > sy:
            x = cx + end * (sx / 2 - 0.13)
            m.box("wood", x - 0.03, x + 0.03, cy - sy / 2 + 0.03, cy + sy / 2 - 0.03, z, z + 0.42)
        else:
            y = cy + end * (sy / 2 - 0.13)
            m.box("wood", cx - sx / 2 + 0.03, cx + sx / 2 - 0.03, y - 0.03, y + 0.03, z, z + 0.42)


def wardrobe(m, x0, x1, y0, y1, z):
    m.box("wood", x0, x1, y0, y1, z, z + 2.0)


def ceiling_fan(m, cx, cy, ceiling):
    m.box("fan", cx - 0.02, cx + 0.02, cy - 0.02, cy + 0.02, ceiling - 0.45, ceiling)
    m.box("fan", cx - 0.12, cx + 0.12, cy - 0.12, cy + 0.12, ceiling - 0.55, ceiling - 0.45)
    for k in range(3):
        a = k * 2.0 * math.pi / 3.0
        m.rbox("fan", cx + math.cos(a) * 0.48, cy + math.sin(a) * 0.48, ceiling - 0.52, ceiling - 0.5, 0.38, 0.06, a)


def sofa(m, cx, cy, z, along_x, length=2.0, back=1):
    d = 0.85
    if along_x:
        m.box("soft", cx - length / 2, cx + length / 2, cy - d / 2, cy + d / 2, z, z + 0.45)
        y = cy + back * (d / 2 - 0.1)
        m.box("soft", cx - length / 2, cx + length / 2, y - 0.1, y + 0.1, z + 0.45, z + 0.85)
    else:
        m.box("soft", cx - d / 2, cx + d / 2, cy - length / 2, cy + length / 2, z, z + 0.45)
        x = cx + back * (d / 2 - 0.1)
        m.box("soft", x - 0.1, x + 0.1, cy - length / 2, cy + length / 2, z + 0.45, z + 0.85)


def tt_table(m, cx, cy, z, along_x=True):
    lx, ly = (1.37, 0.7625) if along_x else (0.7625, 1.37)
    m.box("tt", cx - lx, cx + lx, cy - ly, cy + ly, z + 0.73, z + 0.76)
    for dx in (-1, 1):
        for dy in (-1, 1):
            m.box("metal", cx + dx * (lx - 0.25) - 0.03, cx + dx * (lx - 0.25) + 0.03,
                  cy + dy * (ly - 0.15) - 0.03, cy + dy * (ly - 0.15) + 0.03, z, z + 0.73)
    if along_x:
        m.box("metal", cx - 0.01, cx + 0.01, cy - ly - 0.1, cy + ly + 0.1, z + 0.76, z + 0.91)
    else:
        m.box("metal", cx - lx - 0.1, cx + lx + 0.1, cy - 0.01, cy + 0.01, z + 0.76, z + 0.91)


def _grid(a0, a1, step, margin):
    n = max(1, int((a1 - a0 - 2 * margin) // step) + 1)
    span = (n - 1) * step
    start = (a0 + a1) / 2.0 - span / 2.0
    return [start + i * step for i in range(n)]


def furnish_hall(m, kind: str, rect: Rect, z: float, ceiling: float, entrance_side: str = "front") -> int:
    """Fill a ground-floor hall; returns how many main pieces were placed."""
    x0, x1, y0, y1 = rect
    long_x = (x1 - x0) >= (y1 - y0)
    placed = 0
    if kind == "reception":
        cx, cy = (x0 + x1) / 2.0, y0 + min(4.5, (y1 - y0) * 0.45)
        m.box("wood", cx - 1.8, cx + 1.8, cy, cy + 0.7, z, z + 1.05)                     # reception counter
        m.box("wood", cx - 1.9, cx + 1.9, cy - 0.05, cy + 0.75, z + 1.05, z + 1.1)
        m.box("wood", cx + 1.8, cx + 2.5, cy, cy + 2.2, z, z + 1.05)                     # L return
        chair(m, cx - 0.8, cy + 1.2, z, (0, 1))
        chair(m, cx + 0.8, cy + 1.2, z, (0, 1))
        sx = x0 + 2.0                                                                    # security desk at the door
        m.box("wood", sx - 0.8, sx + 0.8, y0 + 1.5, y0 + 2.1, z, z + 1.0)
        chair(m, sx, y0 + 2.6, z, (0, 1))
        sofa(m, x1 - 2.0, (y0 + y1) / 2.0, z, False, 2.2, 1)
        return 3
    if kind == "mess":
        across = not long_x
        rows = _grid(y0, y1, 2.8, 2.0) if not across else _grid(x0, x1, 2.8, 2.0)
        cols = _grid(x0 + 2.5, x1, 3.4, 1.5) if not across else _grid(y0 + 2.5, y1, 3.4, 1.5)
        for r in rows:
            for c in cols:
                cx, cy = (c, r) if not across else (r, c)
                sx, sy = (2.0, 0.9) if not across else (0.9, 2.0)
                table(m, cx, cy, z, sx, sy)
                if not across:
                    bench(m, cx, cy - 0.75, z, 2.0, 0.32)
                    bench(m, cx, cy + 0.75, z, 2.0, 0.32)
                else:
                    bench(m, cx - 0.75, cy, z, 0.32, 2.0)
                    bench(m, cx + 0.75, cy, z, 0.32, 2.0)
                placed += 1
        if not across:                                                                   # serving counter
            m.box("metal", x0 + 0.4, x0 + 1.2, y0 + 1.0, y1 - 1.0, z, z + 0.95)
        else:
            m.box("metal", x0 + 1.0, x1 - 1.0, y0 + 0.4, y0 + 1.2, z, z + 0.95)
        return placed
    if kind == "recreation":
        along = long_x
        spots = _grid(x0, x1, 4.6, 2.6) if along else _grid(y0, y1, 4.6, 2.6)
        mid = (y0 + y1) / 2.0 if along else (x0 + x1) / 2.0
        for s in spots[:4]:
            tt_table(m, *((s, mid) if along else (mid, s)), z, along_x=along)
            placed += 1
        if along:
            sofa(m, (x0 + x1) / 2.0, y1 - 0.7, z, True, 2.4, 1)
            sofa(m, (x0 + x1) / 2.0 + 3.0, y1 - 0.7, z, True, 2.4, 1)
        else:
            sofa(m, x1 - 0.7, (y0 + y1) / 2.0, z, False, 2.4, 1)
            sofa(m, x1 - 0.7, (y0 + y1) / 2.0 + 3.0, z, False, 2.4, 1)
        return placed
    if kind == "library":
        if long_x:
            for x in _grid(x0, x1 - 4.0, 1.8, 1.2):
                m.box("wood", x - 0.2, x + 0.2, y1 - 3.2, y1 - 0.8, z, z + 2.0)            # shelf rows
                placed += 1
            for x in _grid(x0, x1, 3.2, 2.0)[:5]:
                cy = y0 + 2.2
                table(m, x, cy, z, 1.8, 0.9)
                chair(m, x - 0.5, cy - 0.75, z, (0, -1))
                chair(m, x + 0.5, cy - 0.75, z, (0, -1))
        else:
            for y in _grid(y0, y1 - 4.0, 1.8, 1.2):
                m.box("wood", x1 - 3.2, x1 - 0.8, y - 0.2, y + 0.2, z, z + 2.0)
                placed += 1
            for y in _grid(y0, y1, 3.2, 2.0)[:5]:
                cx = x0 + 2.2
                table(m, cx, y, z, 0.9, 1.8)
                chair(m, cx - 0.75, y - 0.5, z, (-1, 0))
                chair(m, cx - 0.75, y + 0.5, z, (-1, 0))
        return placed
    # study room: rows of desks with chairs
    if long_x:
        for x in _grid(x0, x1, 2.4, 1.5):
            for y in _grid(y0, y1, 2.2, 1.6):
                table(m, x, y, z, 1.4, 0.7)
                chair(m, x, y - 0.65, z, (0, -1))
                placed += 1
    else:
        for y in _grid(y0, y1, 2.4, 1.5):
            for x in _grid(x0, x1, 2.2, 1.6):
                table(m, x, y, z, 0.7, 1.4)
                chair(m, x - 0.65, y, z, (-1, 0))
                placed += 1
    return placed


# ------------------------------------------------------------------ input
@dataclass
class BuildingInput:
    name: str = "building"
    shape: str = "rect"
    width: Optional[float] = None
    depth: Optional[float] = None
    wing_depth: float = 10.0
    floors: int = 4
    floor_height: float = 3.2
    bay_width: float = 3.6
    rooms: Optional[int] = None
    corridor: str = "auto"
    balconies: bool = True
    brick_accents: bool = True
    entrance: bool = True
    sign_text: str = ""
    interior: bool = True
    furnish: bool = True
    facilities: Optional[List[str]] = None
    stair_cores: bool = True
    collections: bool = True
    roof: str = "flat"
    roof_pitch: float = 30.0
    roof_color: Any = None
    wall_color: Any = None
    accent_color: Any = None
    frame_color: Any = None
    glass_color: Any = None
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    yaw_degrees: float = 0.0
    face_towards: Optional[List[float]] = None

    def __post_init__(self):
        self.name = str(self.name or "building").strip().replace(" ", "_") or "building"
        shape = str(self.shape or "rect").strip().lower().replace("-", "").replace("_", "").replace(" ", "")
        shape = {"rectangle": "rect", "block": "rect", "box": "rect", "i": "rect", "lshape": "l", "lshaped": "l",
                 "ushape": "u", "ushaped": "u", "o": "courtyard", "ring": "courtyard", "closed": "courtyard",
                 "square": "courtyard", "oshape": "courtyard", "quad": "courtyard"}.get(shape, shape)
        if shape not in ("rect", "l", "u", "courtyard"):
            raise ValueError("BuildingInput.shape must be rect, L, U or courtyard")
        self.shape = shape
        self.floors = int(_coerce_number(self.floors, "BuildingInput.floors"))
        if not (1 <= self.floors <= 40):
            raise ValueError("BuildingInput.floors (storeys including the ground floor; G+5 = 6) must be 1-40")
        for attr, lo, hi in (("floor_height", 2.6, 6.0), ("bay_width", 2.8, 8.0), ("wing_depth", 6.0, 30.0)):
            value = _coerce_number(getattr(self, attr), f"BuildingInput.{attr}")
            if not (lo <= value <= hi):
                raise ValueError(f"BuildingInput.{attr} must be {lo}-{hi}")
            setattr(self, attr, value)
        self.corridor = str(self.corridor or "auto").strip().lower()
        if self.corridor in ("auto", ""):
            self.corridor = "inside" if self.shape == "rect" else "open"
        if self.corridor in ("gallery", "verandah", "veranda", "external", "outside", "single"):
            self.corridor = "open"
        if self.corridor in ("central", "double", "internal", "middle"):
            self.corridor = "inside"
        if self.corridor not in ("open", "inside"):
            raise ValueError("BuildingInput.corridor must be open (gallery on the courtyard side) or inside")
        if self.rooms is not None:
            self.rooms = int(_coerce_number(self.rooms, "BuildingInput.rooms"))
            if not (1 <= self.rooms <= 2000):
                raise ValueError("BuildingInput.rooms must be 1-2000")
        self._size_from_rooms()
        for attr in ("width", "depth"):
            value = _coerce_number(getattr(self, attr), f"BuildingInput.{attr}")
            if not (8.0 <= value <= 300.0):
                raise ValueError(f"BuildingInput.{attr} must be 8-300 metres")
            setattr(self, attr, value)
        if self.shape != "rect":
            limit = min(self.width, self.depth) / 2.0 - 3.0 if self.shape in ("u", "courtyard") else min(self.width, self.depth) - 4.0
            if self.wing_depth > limit:
                self.wing_depth = max(6.0, limit)
        for attr in ("balconies", "brick_accents", "entrance", "interior", "furnish", "stair_cores", "collections"):
            setattr(self, attr, _coerce_bool(getattr(self, attr), f"BuildingInput.{attr}"))
        self.sign_text = str(self.sign_text or "").strip()[:60]
        roof = str(self.roof or "flat").strip().lower().replace(" ", "_").replace("-", "_")
        roof = ROOF_STYLES.get(roof, ROOF_STYLES.get(roof.replace("_roof", ""), roof))
        if roof not in ("flat", "terrace", "gable", "hip"):
            raise ValueError("BuildingInput.roof must be flat, terrace (roof garden), gable (pitched / sloped) or hip")
        self.roof = roof
        self.roof_pitch = _coerce_number(self.roof_pitch, "BuildingInput.roof_pitch")
        if not (10.0 <= self.roof_pitch <= 60.0):
            raise ValueError("BuildingInput.roof_pitch must be 10-60 degrees")
        from .colors import parse_color
        for attr in ("roof_color", "wall_color", "accent_color", "frame_color", "glass_color"):
            setattr(self, attr, parse_color(getattr(self, attr), f"BuildingInput.{attr}"))
        if self.facilities is None:
            self.facilities = ["reception", "library", "recreation", "mess", "study"]
        else:
            items = self.facilities if isinstance(self.facilities, list) else str(self.facilities).split(",")
            known = {"reception": "reception", "lobby": "reception", "security": "reception", "library": "library",
                     "recreation": "recreation", "rec": "recreation", "games": "recreation", "table_tennis": "recreation",
                     "mess": "mess", "dining": "mess", "canteen": "mess", "cafeteria": "mess", "study": "study",
                     "common_room": "study", "reading": "library"}
            self.facilities = [known.get(str(i).strip().lower().replace(" ", "_").split("_room")[0] or "", None)
                               or known.get(str(i).strip().lower().replace(" ", "_"), "study") for i in items][:6]
        self.location = _vec3(self.location, "BuildingInput.location")
        self.yaw_degrees = _coerce_number(self.yaw_degrees, "BuildingInput.yaw_degrees")
        if self.face_towards is not None:
            target = _coerce_list(self.face_towards, "BuildingInput.face_towards")
            if len(target) not in (2, 3):
                raise ValueError("BuildingInput.face_towards must be [x, y]")
            self.face_towards = target[:2]

    def _size_from_rooms(self):
        """Pick a footprint that holds `rooms` rooms on the upper floors when width/depth were not given."""
        bay, wd = float(_coerce_number(self.bay_width, "bay_width")), float(_coerce_number(self.wing_depth, "wing_depth"))
        if self.width is not None and self.depth is not None:
            return
        upper = max(1, int(_coerce_number(self.floors, "floors")) - 1)
        per_floor = math.ceil(self.rooms / upper) if self.rooms else None
        factor = {"rect": 2.0 if self.corridor == "inside" else 1.0, "l": 1.8, "u": 2.6, "courtyard": 3.4}[self.shape]
        if per_floor:
            bays = max(4, math.ceil(per_floor / factor))
        else:
            bays = 14 if self.shape != "rect" else 12
        if self.width is None:
            self.width = round(bays * bay + (0 if self.shape == "rect" else 0), 2)
        if self.depth is None:
            self.depth = wd if self.shape == "rect" else round(max(wd * 2 + 8, 0.8 * bays * bay + wd), 2)


# ------------------------------------------------------------------ builder
def build(v: BuildingInput):
    """Pure geometry: returns (Mesher, info) in local coordinates."""
    m = Mesher()
    fh, floors = v.floor_height, v.floors
    roof_z = floors * fh
    blocks, court = blocks_for(v.shape, v.width, v.depth, v.wing_depth)
    hx, hy = v.width / 2.0, v.depth / 2.0
    cw = 2.4                                                     # corridor width

    # stair / lift cores: inner corners of the courtyard, or both ends of a rect block
    cores: List[Tuple[Rect, Tuple[float, float]]] = []          # (rect, direction that faces the corridor)
    if v.stair_cores and v.floors >= 2:                 # a one-storey block needs no stair / lift core
        if court is not None:
            cx0, cx1, cy0, cy1 = court
            cores.append(((cx0, cx0 + 6.0, cy0, cy0 + 5.0), (1.0, 1.0)))
            if v.shape in ("u", "courtyard"):
                cores.append(((cx1 - 6.0, cx1, cy0, cy0 + 5.0), (-1.0, 1.0)))
        else:
            cores.append(((-hx + 0.3, -hx + 6.3, -hy + 0.3, hy - 0.3), (1.0, 0.0)))
            cores.append(((hx - 6.3, hx - 0.3, -hy + 0.3, hy - 0.3), (-1.0, 0.0)))
    lifts = [_lift_rect(rect, facing) for rect, facing in cores]
    core_rects = [c[0] for c in cores] + lifts
    faces = exposed_faces(blocks, core_rects if court is not None else [])

    # floor slabs + roof + ground slab, slightly larger than the blocks so they read as bands
    flat = v.roof in ("flat", "terrace")
    for (x0, x1, y0, y1) in blocks:
        m.box("frame", x0 - 0.08, x1 + 0.08, y0 - 0.08, y1 + 0.08, 0.0, 0.15)
        for f in range(1, floors + 1):
            top = 0.15 if f == floors else 0.1
            key = "roof" if (f == floors and flat) else "frame"
            m.box(key, x0 - 0.08, x1 + 0.08, y0 - 0.08, y1 + 0.08, f * fh - 0.1, f * fh + top)
    if not flat:
        _pitched_roofs(m, blocks, roof_z + 0.15, v.roof, v.roof_pitch)

    rooms_per_floor = 0
    room_spots: List[dict] = []
    entrance_info = None
    front_face = None
    if v.entrance:
        fronts = [f for f in faces if f[1] == "front" and f[0] == 0]
        if fronts:
            front_face = fronts[0]

    for (bi, side, line, n, intervals) in faces:
        bx0, bx1, by0, by1 = blocks[bi]
        block_depth = (by1 - by0) if n[1] != 0 else (bx1 - bx0)
        for a, b in intervals:
            mid = (a + b) / 2.0
            px, py = ((mid, line) if n[1] != 0 else (line, mid))
            courtyard_side = _inside(court, px + n[0] * 1.0, py + n[1] * 1.0)
            length = b - a
            is_end = (not courtyard_side) and length <= v.wing_depth + 0.6 and v.shape != "rect" or \
                (v.shape == "rect" and side in ("left", "right"))
            # frame origin = the interval end that makes u run 0..length
            ends = [((a, line) if n[1] != 0 else (line, a)), ((b, line) if n[1] != 0 else (line, b))]
            ux, uy = n[1], -n[0]
            ends.sort(key=lambda p: p[0] * ux + p[1] * uy)
            fr = Frame(m, ends[0], n)
            nb = max(1, int(round(length / v.bay_width)))
            bay = length / nb
            gallery = courtyard_side and v.corridor == "open"
            entrance_bays = set()
            if front_face is not None and (bi, side) == front_face[:2] and (a, b) == front_face[4][0]:
                k = 3 if nb >= 7 else 1
                first = nb // 2 - k // 2
                entrance_bays = set(range(first, first + k))
            # roof parapet (flat roofs) + plinth
            if flat:
                fr.box("roof", -0.02, length + 0.02, -0.22, 0.0, roof_z + 0.15, roof_z + 1.05)
            fr.box("brick" if v.brick_accents else "frame", 0.0, length, 0.0, 0.04, 0.0, 0.6)
            if gallery:
                _gallery(fr, v, nb, bay, length, cw, floors, fh)
                continue
            material = "brick" if (is_end and v.brick_accents) else "wall"
            for f in range(floors):
                z0 = f * fh + (0.15 if f == 0 else 0.1)
                z1 = (f + 1) * fh - 0.1
                for k in range(nb):
                    u0, u1 = k * bay, (k + 1) * bay
                    if f == 0 and k in entrance_bays:
                        continue
                    balcony = (v.balconies and f >= 1 and not is_end and k % 2 == 0)
                    _window_bay(fr, u0, u1, z0, z1, material, door=balcony, narrow=is_end)
                    if balcony:
                        _balcony(fr, u0, u1, f * fh)
                if not is_end and f >= 1:
                    rooms_here = nb if (not courtyard_side or v.corridor == "inside") else 0
                    if f == 1:
                        rooms_per_floor += rooms_here
            # brick fins every 2 bays on long outer faces
            if v.brick_accents and not is_end:
                for k in range(0, nb + 1, 2):
                    u = k * bay
                    if any(abs(u - e * bay) < 1e-6 or abs(u - (e + 1) * bay) < 1e-6 for e in entrance_bays):
                        continue
                    fr.box("brick", u - 0.2, u + 0.2, 0.0, 0.3, 0.6, roof_z + (1.05 if flat else 0.1))
            if entrance_bays:
                entrance_info = _entrance(fr, v, min(entrance_bays) * bay, (max(entrance_bays) + 1) * bay, fh)
            # rooms behind this face
            if v.interior and not is_end:
                if v.corridor == "open":
                    depth = max(3.0, block_depth - cw - WALL_T)
                else:
                    depth = max(3.0, (block_depth - cw) / 2.0)
                in_core = [any(_inside(r, *fr.pt((k + 0.5) * bay, -depth / 2.0)) for r in core_rects)
                           for k in range(nb)]
                for f in range(1, floors):
                    zf = f * fh + 0.1
                    ceiling = (f + 1) * fh - 0.1
                    for k in range(1, nb):
                        if not (in_core[k - 1] and in_core[k]):
                            fr.box("rooms", k * bay - 0.06, k * bay + 0.06, -depth, -WALL_T, zf, ceiling)
                    for k in range(nb):
                        if in_core[k]:
                            continue
                        u0, u1 = k * bay, (k + 1) * bay
                        if v.corridor == "inside":                   # corridor wall with a door per room
                            fr.box("rooms", u0, u0 + 0.5, -depth - 0.1, -depth, zf, ceiling)
                            fr.box("rooms", u0 + 1.4, u1, -depth - 0.1, -depth, zf, ceiling)
                            fr.box("rooms", u0 + 0.5, u0 + 1.4, -depth - 0.1, -depth, zf + 2.1, ceiling)
                            fr.box("door", u0 + 0.52, u0 + 1.38, -depth - 0.07, -depth - 0.03, zf, zf + 2.08)
                        if v.furnish:
                            _furnish_room(fr, u0, u1, depth, zf, ceiling)
                            if len(room_spots) < 60:
                                room_spots.append({"floor": f, "local": fr.pt((u0 + u1) / 2.0, -depth / 2.0)})

    # ground-floor halls and partitions
    facilities_placed = []
    if v.interior:
        zones = _ground_zones(blocks, court, v, cw)
        for zone, kind in zip(zones, v.facilities):
            count = furnish_hall(m, kind, zone, 0.15, fh - 0.1) if v.furnish else 0
            for lx in _grid(zone[0], zone[1], 4.0, 1.5):
                for ly in _grid(zone[2], zone[3], 4.0, 1.5):
                    m.box("lamp", lx - 0.3, lx + 0.3, ly - 0.3, ly + 0.3, fh - 0.14, fh - 0.1)
            facilities_placed.append({"kind": kind, "local_rect": zone, "pieces": count})
        for i, zone in enumerate(zones):                      # hall partitions with a 1.6 m doorway
            for j, other in enumerate(zones):
                if i == j:
                    continue
                if abs(zone[1] - other[0]) < 0.05 and zone[2] < other[3] and other[2] < zone[3]:
                    y0, y1 = max(zone[2], other[2]), min(zone[3], other[3])
                    m.box("rooms", zone[1] - 0.08, zone[1] + 0.08, y0 - 0.4, y1 - 1.6, 0.15, fh - 0.1)
            if i >= 3:                                        # wing halls: wall where the wing meets the front block
                x0, x1, y0, _y1 = zone
                m.box("rooms", x0 - 0.4, x1 - 1.6, y0 - 0.48, y0 - 0.32, 0.15, fh - 0.1)

    # cores: stairs + lift shaft, headroom and water tanks
    core_info = []
    for rect, facing in cores:
        core_info.append(_core(m, rect, facing, floors, fh, v.brick_accents, headroom=flat))
    if v.roof == "terrace":
        _roof_garden(m, blocks, roof_z + 0.15)
    for (x0, x1, y0, y1) in (blocks if v.roof == "flat" else []):     # water tanks on a plain flat roof
        if (x1 - x0) * (y1 - y0) > 120:
            cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            m.box("metal", cx - 1.0, cx + 1.0, cy - 1.0, cy + 1.0, roof_z + 0.15, roof_z + 1.9)

    info = {
        "blocks": blocks, "court": court, "rooms_per_floor": rooms_per_floor,
        "rooms": rooms_per_floor * max(0, floors - 1), "entrance": entrance_info, "room_spots": room_spots,
        "facilities": facilities_placed, "cores": core_info,
        "height": round(roof_z + (1.05 if flat else 0.15 + _ridge_height(blocks, v.roof_pitch)), 2),
    }
    return m, info


def _window_bay(fr: Frame, u0, u1, z0, z1, material, door=False, narrow=False):
    bay = u1 - u0
    uc = (u0 + u1) / 2.0
    if door:
        ww, sill, head = min(1.2, bay * 0.4), z0, min(z0 + 2.2, z1 - 0.2)
    elif narrow:
        ww, sill, head = min(0.7, bay * 0.25), z0 + 0.6, min(z0 + 2.3, z1 - 0.2)
    else:
        ww, sill, head = min(1.8, bay * 0.5), z0 + 0.9, min(z0 + 2.2, z1 - 0.2)
    wl, wr = uc - ww / 2.0, uc + ww / 2.0
    t = -WALL_T
    fr.box(material, u0, u1, t, 0.0, z0, sill)
    fr.box(material, u0, u1, t, 0.0, head, z1)
    fr.box(material, u0, wl, t, 0.0, sill, head)
    fr.box(material, wr, u1, t, 0.0, sill, head)
    fr.box("glass", wl, wr, -0.15, -0.11, sill, head)
    f = 0.05
    fr.box("metal", wl, wr, -0.17, -0.06, sill, sill + f)
    fr.box("metal", wl, wr, -0.17, -0.06, head - f, head)
    fr.box("metal", wl, wl + f, -0.17, -0.06, sill, head)
    fr.box("metal", wr - f, wr, -0.17, -0.06, sill, head)
    fr.box("metal", uc - f / 2, uc + f / 2, -0.17, -0.06, sill, head)
    if not door:
        fr.box("frame", wl - 0.05, wr + 0.05, 0.0, 0.06, sill - 0.06, sill)          # sill ledge


def _railing(fr: Frame, u0, u1, v0, v1, z, along_v=False, spacing=0.3, height=1.0):
    """Top rail + balusters on the line u0..u1 at v0..v1 (or along v when along_v)."""
    if along_v:
        fr.box("metal", u0, u1, v0, v1, z + height - 0.05, z + height)
        n = max(1, int((v1 - v0) / spacing))
        for i in range(n + 1):
            v = v0 + (v1 - v0) * i / n
            fr.box("metal", u0, u1, v - 0.02, v + 0.02, z, z + height - 0.05)
    else:
        fr.box("metal", u0, u1, v0, v1, z + height - 0.05, z + height)
        fr.box("metal", u0, u1, v0, v1, z + 0.1, z + 0.14)
        n = max(1, int((u1 - u0) / spacing))
        for i in range(n + 1):
            u = u0 + (u1 - u0) * i / n
            fr.box("metal", u - 0.02, u + 0.02, v0, v1, z, z + height - 0.05)


def _balcony(fr: Frame, u0, u1, z_floor):
    bay = u1 - u0
    w = min(2.6, bay - 0.5)
    a, b = (u0 + u1) / 2.0 - w / 2.0, (u0 + u1) / 2.0 + w / 2.0
    fr.box("frame", a, b, 0.0, 1.2, z_floor - 0.1, z_floor + 0.1)
    top = z_floor + 0.1
    _railing(fr, a, b, 1.15, 1.2, top)
    _railing(fr, a, a + 0.05, 0.0, 1.15, top, along_v=True)
    _railing(fr, b - 0.05, b, 0.0, 1.15, top, along_v=True)


def _gallery(fr: Frame, v: BuildingInput, nb, bay, length, cw, floors, fh):
    """Open corridor on a courtyard side: columns on the edge, railings, and the room wall with doors behind."""
    for k in range(nb + 1):
        u = min(max(k * bay, 0.18), length - 0.18)
        fr.box("frame", u - 0.18, u + 0.18, -0.36, 0.0, 0.0, floors * fh)
    for f in range(floors):
        z0 = f * fh + (0.15 if f == 0 else 0.1)
        z1 = (f + 1) * fh - 0.1
        if f >= 1:
            _railing(fr, 0.2, length - 0.2, -0.12, -0.07, z0)
        wv0, wv1 = -cw - WALL_T, -cw
        for k in range(nb):
            u0, u1 = k * bay, (k + 1) * bay
            if f == 0:                                            # halls: big glazing, a door every 3rd bay
                if k % 3 == 1:
                    d0, d1 = (u0 + u1) / 2.0 - 0.9, (u0 + u1) / 2.0 + 0.9
                    fr.box("wall", u0, d0, wv0, wv1, z0, z1)
                    fr.box("wall", d1, u1, wv0, wv1, z0, z1)
                    fr.box("wall", d0, d1, wv0, wv1, z0 + 2.4, z1)
                    fr.box("glass", d0 + 0.05, d1 - 0.05, wv1 - 0.14, wv1 - 0.1, z0, z0 + 2.38)
                    fr.box("metal", d0, d1, wv1 - 0.16, wv1 - 0.08, z0 + 2.33, z0 + 2.4)
                else:
                    g0, g1 = u0 + 0.3, u1 - 0.3
                    fr.box("wall", u0, g0, wv0, wv1, z0, z1)
                    fr.box("wall", g1, u1, wv0, wv1, z0, z1)
                    fr.box("wall", g0, g1, wv0, wv1, z0, z0 + 0.4)
                    fr.box("wall", g0, g1, wv0, wv1, z0 + 2.6, z1)
                    fr.box("glass", g0, g1, wv1 - 0.14, wv1 - 0.1, z0 + 0.4, z0 + 2.6)
                    fr.box("metal", g0, g1, wv1 - 0.16, wv1 - 0.08, z0 + 0.4, z0 + 0.45)
                    fr.box("metal", g0, g1, wv1 - 0.16, wv1 - 0.08, z0 + 2.55, z0 + 2.6)
                continue
            d0, d1 = u0 + 0.4, u0 + 1.3                              # room door
            w0, w1 = min(u1 - 1.6, d1 + 0.5), u1 - 0.4                 # room window
            fr.box("wall", u0, d0, wv0, wv1, z0, z1)
            fr.box("wall", d0, d1, wv0, wv1, z0 + 2.1, z1)
            fr.box("door", d0, d1, wv1 - 0.12, wv1 - 0.06, z0, z0 + 2.1)
            fr.box("metal", d1 - 0.18, d1 - 0.1, wv1 - 0.04, wv1 + 0.02, z0 + 1.0, z0 + 1.06)
            if w1 - w0 > 0.6:
                fr.box("wall", d1, w0, wv0, wv1, z0, z1)
                fr.box("wall", w0, w1, wv0, wv1, z0, z0 + 1.0)
                fr.box("wall", w0, w1, wv0, wv1, z0 + 2.1, z1)
                fr.box("wall", w1, u1, wv0, wv1, z0, z1)
                fr.box("glass", w0, w1, wv1 - 0.14, wv1 - 0.1, z0 + 1.0, z0 + 2.1)
                fr.box("metal", w0, w1, wv1 - 0.16, wv1 - 0.08, z0 + 1.0, z0 + 1.05)
                fr.box("metal", w0, w1, wv1 - 0.16, wv1 - 0.08, z0 + 2.05, z0 + 2.1)
            else:
                fr.box("wall", d1, u1, wv0, wv1, z0, z1)


def _entrance(fr: Frame, v: BuildingInput, u0, u1, fh):
    """Glass front with double doors, canopy on 2 columns, steps. Returns the sign / door positions (local)."""
    z0, z1 = 0.15, fh - 0.1
    fr.box("glass", u0 + 0.1, u1 - 0.1, -0.16, -0.12, z0, z1)
    n = max(2, int((u1 - u0) / 1.2))
    for i in range(n + 1):
        u = u0 + 0.1 + (u1 - u0 - 0.2) * i / n
        fr.box("metal", u - 0.04, u + 0.04, -0.2, -0.08, z0, z1)
    fr.box("metal", u0 + 0.1, u1 - 0.1, -0.2, -0.08, z0 + 2.45, z0 + 2.55)
    uc = (u0 + u1) / 2.0
    fr.box("door", uc - 1.2, uc - 0.03, -0.1, -0.04, z0, z0 + 2.4)                      # double doors (wood-framed)
    fr.box("door", uc + 0.03, uc + 1.2, -0.1, -0.04, z0, z0 + 2.4)
    fr.box("glass", uc - 1.05, uc - 0.18, -0.04, -0.02, z0 + 0.3, z0 + 2.2)
    fr.box("glass", uc + 0.18, uc + 1.05, -0.04, -0.02, z0 + 0.3, z0 + 2.2)
    a, b = u0 - 0.6, u1 + 0.6
    cz = fh - 0.1
    fr.box("frame", a, b, 0.0, 4.0, cz - 0.05, cz + 0.25)                              # canopy slab
    fr.box("frame", a, b, 3.85, 4.05, cz - 0.45, cz + 1.25)                            # tall fascia: the name board
    for u in (a + 0.4, b - 0.4):
        fr.box("frame", u - 0.2, u + 0.2, 3.4, 3.8, 0.0, cz - 0.05)
    fr.box("frame", a, b, 0.0, 4.4, 0.0, 0.15)                                         # landing
    fr.box("frame", a - 0.4, b + 0.4, 4.4, 4.8, 0.0, 0.075)                            # step
    return {"door_local": fr.pt(uc, 0.0), "out_local": fr.pt(uc, 7.0), "sign_local": fr.pt(uc, 4.07),
            "sign_z": cz + 0.4, "normal": (fr.nx, fr.ny), "width": round(b - a, 2)}


def _furnish_room(fr: Frame, u0, u1, depth, zf, ceiling):
    """Bed, study desk + chair, wardrobe and a ceiling fan in one room (frame coords: v < 0 is inside)."""
    m = fr.m

    def B(key, a0, a1, b0, b1, z0, z1):            # room coords: a along the wall, b = depth from the wall
        fr.box(key, a0, a1, -b1, -b0, z0, z1)

    w = u1 - u0
    if w < 2.6 or depth < 3.0:
        return
    i0 = WALL_T + 0.05
    # bed along the left partition, head at the window wall
    a0, a1 = u0 + 0.12, u0 + 1.07
    B("wood", a0, a1, i0, i0 + 2.0, zf + 0.08, zf + 0.35)
    B("wood", a0, a1, i0 - 0.05, i0, zf, zf + 0.9)
    B("soft", a0 + 0.03, a1 - 0.03, i0 + 0.03, i0 + 1.97, zf + 0.35, zf + 0.52)
    B("soft", a0 + 0.12, a1 - 0.12, i0 + 0.08, i0 + 0.5, zf + 0.52, zf + 0.62)
    for la, lb in ((a0, i0 + 1.9), (a1 - 0.06, i0 + 1.9)):
        B("wood", la, la + 0.06, lb, lb + 0.06, zf, zf + 0.08)
    # study desk under the window side, against the right partition
    d0, d1 = u1 - 1.3, u1 - 0.12
    B("wood", d0, d1, i0, i0 + 0.6, zf + 0.72, zf + 0.76)
    for la in (d0, d1 - 0.05):
        for lb in (i0, i0 + 0.55):
            B("wood", la, la + 0.05, lb, lb + 0.05, zf, zf + 0.72)
    cu = (d0 + d1) / 2.0
    B("wood", cu - 0.22, cu + 0.22, i0 + 0.75, i0 + 1.19, zf + 0.43, zf + 0.47)          # chair seat
    for la in (cu - 0.2, cu + 0.16):
        for lb in (i0 + 0.77, i0 + 1.15):
            B("wood", la, la + 0.04, lb, lb + 0.04, zf, zf + 0.43)
    B("wood", cu - 0.22, cu + 0.22, i0 + 1.15, i0 + 1.19, zf + 0.47, zf + 0.92)          # chair back
    # wardrobe near the door end, right side
    if depth > 3.4:
        B("wood", u1 - 1.0, u1 - 0.1, depth - 0.75, depth - 0.15, zf, zf + 2.0)
        B("metal", u1 - 0.57, u1 - 0.53, depth - 0.78, depth - 0.75, zf + 0.9, zf + 1.2)
    # ceiling fan in the middle of the room, a tube light over the window half
    cx, cy = fr.pt((u0 + u1) / 2.0, -depth / 2.0)
    ceiling_fan(m, cx, cy, ceiling)
    fr.box("lamp", (u0 + u1) / 2.0 - 0.6, (u0 + u1) / 2.0 + 0.6, -1.25, -1.15, ceiling - 0.05, ceiling - 0.01)


def _ground_zones(blocks: List[Rect], court: Optional[Rect], v: BuildingInput, cw: float) -> List[Rect]:
    """Ground-floor halls in order: entrance zone of the front block, its two sides, then the wings."""
    zones: List[Rect] = []
    inset = 0.4
    gallery = 0.0 if v.corridor == "inside" else cw + WALL_T
    x0, x1, y0, y1 = blocks[0]
    back = y1 - (gallery if court is not None else 0.0)
    third = (x1 - x0) / 3.0
    zones.append((x0 + third, x1 - third, y0 + inset, back - inset))
    zones.append((x0 + inset, x0 + third, y0 + inset, back - inset))
    zones.append((x1 - third, x1 - inset, y0 + inset, back - inset))
    for bx0, bx1, by0, by1 in blocks[1:3]:
        if court is not None and bx1 <= court[0] + 1e-6:              # left wing: gallery on +X
            zones.append((bx0 + inset, bx1 - gallery - inset, by0 + inset, by1 - inset))
        elif court is not None and bx0 >= court[1] - 1e-6:           # right wing: gallery on -X
            zones.append((bx0 + gallery + inset, bx1 - inset, by0 + inset, by1 - inset))
    return [z for z in zones if z[1] - z[0] > 3.0 and z[3] - z[2] > 3.0]


def _lift_rect(rect: Rect, facing) -> Rect:
    x0, x1, y0, y1 = rect
    fx, fy = facing
    if (x1 - x0) >= (y1 - y0):
        lx0 = x1 - 2.4 if fx < 0 else x0
        ly0 = y1 if fy > 0 else y0 - 2.4
        return (lx0, lx0 + 2.4, ly0, ly0 + 2.4)
    lx0 = x1 if fx > 0 else x0 - 2.4
    return (lx0, lx0 + 2.4, (y0 + y1) / 2.0 - 1.2, (y0 + y1) / 2.0 + 1.2)


def _ridge_height(blocks, pitch) -> float:
    return max((min(b[1] - b[0], b[3] - b[2]) / 2.0 + 0.6) * math.tan(math.radians(pitch)) for b in blocks)


def _pitched_roofs(m: Mesher, blocks, base_z: float, style: str, pitch: float, overhang: float = 0.6) -> None:
    """One solid roof per block: gable (ridge along the long side, vertical triangular ends) or hip (sloped on all
    four sides). Each is one 8-corner solid whose top face shrinks to the ridge line."""
    for (x0, x1, y0, y1) in blocks:
        x0, x1, y0, y1 = x0 - overhang, x1 + overhang, y0 - overhang, y1 + overhang
        along_x = (x1 - x0) >= (y1 - y0)
        half = ((y1 - y0) if along_x else (x1 - x0)) / 2.0
        top = base_z + half * math.tan(math.radians(pitch))
        inset = half if style == "hip" else 0.0
        bottom = [(x0, y0, base_z), (x1, y0, base_z), (x1, y1, base_z), (x0, y1, base_z)]
        if along_x:
            cy = (y0 + y1) / 2.0
            a, b = min(x0 + inset, (x0 + x1) / 2.0), max(x1 - inset, (x0 + x1) / 2.0)
            ridge = [(a, cy, top), (b, cy, top), (b, cy, top), (a, cy, top)]
        else:
            cx = (x0 + x1) / 2.0
            a, b = min(y0 + inset, (y0 + y1) / 2.0), max(y1 - inset, (y0 + y1) / 2.0)
            ridge = [(cx, a, top), (cx, a, top), (cx, b, top), (cx, b, top)]
        m.boxes["roof"].append(bottom + ridge)
        # a thin fascia band under the eaves so the roof edge reads clearly
        m.box("frame", x0, x1, y0, y0 + 0.08, base_z - 0.25, base_z)
        m.box("frame", x0, x1, y1 - 0.08, y1, base_z - 0.25, base_z)


def _roof_garden(m: Mesher, blocks, z: float) -> None:
    """Terrace roof: planter beds along the parapet and a wooden pergola in the middle of each block."""
    for (x0, x1, y0, y1) in blocks:
        m.box("garden", x0 + 0.4, x1 - 0.4, y0 + 0.4, y0 + 1.4, z, z + 0.5)
        m.box("garden", x0 + 0.4, x1 - 0.4, y1 - 1.4, y1 - 0.4, z, z + 0.5)
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        w, d = min(8.0, (x1 - x0) * 0.4), min(4.0, (y1 - y0) * 0.3)
        for px in (cx - w / 2, cx + w / 2):
            for py in (cy - d / 2, cy + d / 2):
                m.box("wood", px - 0.1, px + 0.1, py - 0.1, py + 0.1, z, z + 2.6)
        k = 0
        while k * 0.6 <= w:
            bx = cx - w / 2 + k * 0.6
            m.box("wood", bx - 0.04, bx + 0.04, cy - d / 2 - 0.3, cy + d / 2 + 0.3, z + 2.6, z + 2.75)
            k += 1


def _core(m: Mesher, rect: Rect, facing, floors, fh, brick, headroom: bool = True) -> dict:
    """Stair core (walls with a glazed strip, two flights per floor) + a lift shaft, rising above a flat roof
    (kept under a pitched roof)."""
    x0, x1, y0, y1 = rect
    top = floors * fh + (3.0 if headroom else 0.0)
    key = "brick" if brick else "frame"
    t = 0.25
    long_x = (x1 - x0) >= (y1 - y0)
    # walls with a glass strip in the middle of each side
    for (a0, a1, b0, b1, along_x) in ((x0, x1, y0, y0 + t, True), (x0, x1, y1 - t, y1, True),
                                      (x0, x0 + t, y0, y1, False), (x1 - t, x1, y0, y1, False)):
        if along_x:
            mid = (a0 + a1) / 2.0
            m.box(key, a0, mid - 0.6, b0, b1, 0.0, top)
            m.box(key, mid + 0.6, a1, b0, b1, 0.0, top)
            m.box("glass", mid - 0.6, mid + 0.6, b0 + 0.1, b1 - 0.1, 0.3, top - 0.5)
            m.box(key, mid - 0.6, mid + 0.6, b0, b1, top - 0.5, top)
            m.box(key, mid - 0.6, mid + 0.6, b0, b1, 0.0, 0.3)
        else:
            mid = (b0 + b1) / 2.0
            m.box(key, a0, a1, b0, mid - 0.6, 0.0, top)
            m.box(key, a0, a1, mid + 0.6, b1, 0.0, top)
            m.box("glass", a0 + 0.1, a1 - 0.1, mid - 0.6, mid + 0.6, 0.3, top - 0.5)
            m.box(key, a0, a1, mid - 0.6, mid + 0.6, top - 0.5, top)
            m.box(key, a0, a1, mid - 0.6, mid + 0.6, 0.0, 0.3)
    m.box("frame", x0 - 0.1, x1 + 0.1, y0 - 0.1, y1 + 0.1, top, top + 0.2)
    # stairs: two flights per floor (along the long side), landings at each end
    steps = 10
    rise = fh / 2.0 / steps
    if long_x:
        run0, run1 = x0 + 1.4, x1 - 1.4
        lanes = ((y0 + t + 0.1, (y0 + y1) / 2.0 - 0.1), ((y0 + y1) / 2.0 + 0.1, y1 - t - 0.1))
    else:
        run0, run1 = y0 + 1.4, y1 - 1.4
        lanes = ((x0 + t + 0.1, (x0 + x1) / 2.0 - 0.1), ((x0 + x1) / 2.0 + 0.1, x1 - t - 0.1))
    tread = (run1 - run0) / steps
    for f in range(floors):
        base = f * fh + 0.1
        for flight, (l0, l1) in enumerate(lanes):
            for s in range(steps):
                z = base + (s + flight * steps) * rise
                p = run0 + s * tread if flight == 0 else run1 - (s + 1) * tread
                if long_x:
                    m.box("stairs", p, p + tread, l0, l1, z, z + rise)
                else:
                    m.box("stairs", l0, l1, p, p + tread, z, z + rise)
            mid_z = base + fh / 2.0
        if long_x:
            m.box("stairs", run1, x1 - t, y0 + t, y1 - t, mid_z - 0.1, mid_z)
        else:
            m.box("stairs", x0 + t, x1 - t, run1, y1 - t, mid_z - 0.1, mid_z)
    # lift shaft next to the core, on the corridor side
    fx, fy = facing
    lift = _lift_rect(rect, facing)
    m.box(key, lift[0], lift[1], lift[2], lift[3], 0.0, top + (1.0 if headroom else 0.0))
    for f in range(floors):                                          # lift doors on every floor
        z = f * fh + 0.12
        if long_x:
            yy = lift[3] if fy > 0 else lift[2]
            m.box("metal", (lift[0] + lift[1]) / 2 - 0.55, (lift[0] + lift[1]) / 2 + 0.55,
                  yy - 0.03, yy + 0.03, z, z + 2.1)
        else:
            xx = lift[1] if fx > 0 else lift[0]
            m.box("metal", xx - 0.03, xx + 0.03, (lift[2] + lift[3]) / 2 - 0.55,
                  (lift[2] + lift[3]) / 2 + 0.55, z, z + 2.1)
    return {"stairs_local": ((x0 + x1) / 2.0, (y0 + y1) / 2.0), "lift_local": ((lift[0] + lift[1]) / 2.0,
                                                                               (lift[2] + lift[3]) / 2.0)}


# ------------------------------------------------------------------ the tool
def _world(location, yaw, p):
    c, s = math.cos(yaw), math.sin(yaw)
    return [round(location[0] + c * p[0] - s * p[1], 2), round(location[1] + s * p[0] + c * p[1], 2)]


def _collection_names(name: str) -> Dict[str, str]:
    title = "_".join(part.capitalize() for part in name.split("_") if part) or "Building"
    return {"building": f"{title}_Building", "rooms": "Rooms", "furniture": "Furniture"}


class MeshBuildingTool(Tool):
    name = "mesh.building"
    description = (
        "Builds a COMPLETE multi-storey building in one call - hostel, hotel, college block, office, apartment, "
        "hospital, school. shape rect | L | U | courtyard; floors = storeys INCLUDING the ground floor (G+5 = 6); "
        "floor_height (3.2); rooms = how many rooms you want (the footprint is sized for it) or width / depth in "
        "metres; wing_depth = thickness of each wing. It makes the floor slabs, columns, a window per bay with "
        "frames and glass, balconies with railings, red-brick accents, open corridors with railings and room doors "
        "on the courtyard side, the entrance (glass front, double door, canopy, steps) with sign_text as 3D "
        "letters, stair cores with real stair flights, lift shafts, roof parapet and water tanks, AND the inside: "
        "every room has a bed, study desk, chair, wardrobe and ceiling fan; the ground floor has halls for "
        "`facilities` (reception + security desk, mess / dining with tables and benches, recreation with "
        "table-tennis tables and sofas, library with shelves and reading tables, study room). The entrance faces "
        "-Y (turn with yaw_degrees / face_towards); for U the courtyard opens to +Y. roof = flat (parapet + water "
        "tanks), terrace (roof garden with planters and a pergola), gable (pitched / sloped, tiled) or hip; "
        "roof_pitch in degrees. Colours: wall_color, accent_color (the brick parts), roof_color, frame_color "
        "(slabs / columns), glass_color - a colour word ('cream', 'sky blue', 'maroon') or [r, g, b]. EDITING: call "
        "it again with the SAME name and only what should change (e.g. name='hostel', roof='hip' or "
        "wall_color='light yellow') - that building is rebuilt in place, everything else stays. Returns where the "
        "entrance, courtyard and halls are - put paths, gardens and courts there. Never build these parts again "
        "with cubes."
    )
    permission = Permission.SAFE_WRITE
    input_model = BuildingInput

    def __init__(self, bridge):
        self._bridge = bridge

    def execute(self, input_data: Dict[str, Any] = None) -> ToolResult:
        """Same name as an existing building = change THAT building: the new arguments are merged into the ones it
        was built with ('roof': 'hip' keeps its floors, shape, place and colours) and it is rebuilt in place."""
        args = {k: v for k, v in dict(input_data or {}).items() if v is not None}
        name = str(args.get("name") or "building").strip().replace(" ", "_") or "building"
        replace = _coerce_bool(args.pop("replace", True), "replace")
        previous = self._previous(name) if replace else None
        old_parts = []
        if previous is not None:
            old_parts = previous.get("objects") or []
            merged = dict(previous.get("args") or {})
            merged.update(args)
            args = merged
        else:
            old_parts = self._existing_parts(name) if replace else []
        args["name"] = name
        if old_parts:
            try:                                             # check the new arguments before removing anything
                self.validate(dict(args))
            except Exception as exc:  # noqa: BLE001
                return ToolResult.fail(str(exc))
            for part in old_parts:
                try:
                    if self._bridge.get_object(part) is not None:
                        self._bridge.delete_object(part)
                except Exception:  # noqa: BLE001
                    pass
        result = super().execute(args)
        if result.success:
            record = {"args": args, "objects": list(result.data.get("objects", []))}
            BUILT[name] = record
            setter = getattr(self._bridge, "set_custom_prop", None)
            if callable(setter):
                try:
                    setter(f"{name}_structure", "aiagent_building", json.dumps(record, default=str))
                except Exception:  # noqa: BLE001
                    pass
            if old_parts:
                result.data["rebuilt"] = True
                result.data["note"] = (f"'{name}' was rebuilt in place with the changes; everything else is as before. "
                                       + result.data.get("note", ""))
        return result

    def _previous(self, name: str) -> Optional[dict]:
        if name in BUILT:
            return BUILT[name]
        getter = getattr(self._bridge, "get_custom_prop", None)
        if callable(getter):
            try:
                raw = getter(f"{name}_structure", "aiagent_building")
                if raw:
                    return json.loads(raw)
            except Exception:  # noqa: BLE001
                return None
        return None

    def _existing_parts(self, name: str) -> List[str]:
        """A building made before its arguments were remembered: its parts by their known names."""
        try:
            names = {getattr(o, "name", "") for o in self._bridge.get_objects()}
        except Exception:  # noqa: BLE001
            return []
        if f"{name}_structure" not in names:
            return []
        suffixes = [b[0] for b in BUCKETS.values()] + ["_sign"]
        return [f"{name}{s}" for s in suffixes if f"{name}{s}" in names]

    def run(self, v: BuildingInput) -> ToolResult:
        yaw = math.radians(v.yaw_degrees)
        if v.face_towards is not None:
            fx, fy = v.face_towards[0] - v.location[0], v.face_towards[1] - v.location[1]
            if abs(fx) + abs(fy) > 1e-6:
                yaw = math.atan2(fy, fx) - math.atan2(-1.0, 0.0)          # front is -Y
        mesher, info = build(v)
        bridge = self._bridge
        rotation = [0.0, 0.0, yaw]
        created: Dict[str, List[str]] = {"building": [], "rooms": [], "furniture": []}
        materials: Dict[str, Optional[str]] = {}
        for key, (suffix, mat_name, recipe, params, role) in BUCKETS.items():
            if not mesher.boxes[key]:
                continue
            mat_name, recipe, params = _bucket_material(v, key, mat_name, recipe, params)
            verts, faces = mesher.mesh(key)
            obj = bridge.create_mesh(name=f"{v.name}{suffix}", vertices=verts, faces=faces,
                                     location=list(v.location), rotation=rotation, scale=[1.0, 1.0, 1.0])
            obj_name = getattr(obj, "name", f"{v.name}{suffix}")
            if mat_name not in materials:
                materials[mat_name] = _material(bridge, mat_name, recipe, params, fresh=True)
            if materials[mat_name]:
                try:
                    bridge.assign_material(obj_name, materials[mat_name])
                except Exception:  # noqa: BLE001
                    pass
            created[role].append(obj_name)

        sign = None
        entrance = info["entrance"]
        if entrance and v.sign_text and hasattr(bridge, "create_text"):
            sx, sy = _world(v.location, yaw, entrance["sign_local"])
            nx, ny = entrance["normal"]
            text_yaw = yaw + math.atan2(ny, nx) + math.pi / 2.0
            try:
                text = bridge.create_text(name=f"{v.name}_sign", body=v.sign_text,
                                          location=[sx, sy, v.location[2] + entrance["sign_z"]],
                                          rotation=[math.pi / 2.0, 0.0, text_yaw],
                                          size=min(0.9, max(0.25, entrance["width"] * 0.88 / max(4.0, len(v.sign_text) * 0.62))),
                                          extrude=0.03, align="CENTER")
                sign = getattr(text, "name", f"{v.name}_sign")
                mat = _material(bridge, f"{v.name}_sign_mat", "paint", {"color": [0.03, 0.08, 0.3, 1.0], "roughness": 0.35})
                if mat:
                    bridge.assign_material(sign, mat)
                created["building"].append(sign)
            except Exception:  # noqa: BLE001 - the sign is a bonus
                sign = None

        collections = {}
        if v.collections and hasattr(bridge, "move_to_collection"):
            names = _collection_names(v.name)
            for role, objs in created.items():
                if objs:
                    try:
                        bridge.move_to_collection(objs, names[role])
                        collections[names[role]] = list(objs)
                    except Exception:  # noqa: BLE001
                        pass

        loc = v.location
        result = {
            "objects": [o for objs in created.values() for o in objs],
            "shape": v.shape.upper() if len(v.shape) == 1 else v.shape, "roof": v.roof,
            "floors": v.floors, "storeys": f"G+{v.floors - 1}", "floor_height": v.floor_height,
            "height_m": info["height"], "width": round(v.width, 2), "depth": round(v.depth, 2),
            "rooms": info["rooms"], "rooms_per_floor": info["rooms_per_floor"],
            "footprint_world": _footprint(info["blocks"], loc, yaw),
            "yaw_degrees": round(math.degrees(yaw), 1),
            "boxes": mesher.count(),
        }
        if info["court"] is not None:
            c = info["court"]
            result["courtyard"] = {"centre": _world(loc, yaw, ((c[0] + c[1]) / 2.0, (c[2] + c[3]) / 2.0)),
                                   "size": [round(c[1] - c[0], 2), round(c[3] - c[2], 2)],
                                   "note": "open ground - put the garden, paths, benches and trees here"}
        if entrance:
            result["entrance"] = {"door": _world(loc, yaw, entrance["door_local"]),
                                  "path_start": _world(loc, yaw, entrance["out_local"])}
        if sign:
            result["sign"] = sign
        result["halls"] = [{"kind": h["kind"], "centre": _world(loc, yaw, ((h["local_rect"][0] + h["local_rect"][1]) / 2.0,
                                                                         (h["local_rect"][2] + h["local_rect"][3]) / 2.0)),
                            "furniture_pieces": h["pieces"]} for h in info["facilities"]]
        result["stair_cores"] = [_world(loc, yaw, c["stairs_local"]) for c in info["cores"]]
        result["lift_shafts"] = [_world(loc, yaw, c["lift_local"]) for c in info["cores"]]
        if collections:
            result["collections"] = {k: len(o) for k, o in collections.items()}
        result["note"] = ("Done: floors, windows, balconies, railings, corridors, entrance, stairs, lifts, rooms with "
                          "furniture and ground-floor halls are built and have materials - do not add boxes for "
                          "them. To CHANGE this building later (roof style, colours, floors, balconies ...), call "
                          f"mesh.building(name='{v.name}', <only what changes>) - it is rebuilt in place. Next: "
                          "landscape the courtyard, lay paths from entrance.path_start, add courts / parking outside "
                          "the footprint.")
        return ToolResult.ok(result)


# buildings made in this session: name -> {"args": ..., "objects": [...]} (also stored on <name>_structure)
BUILT: Dict[str, dict] = {}


def _bucket_material(v: "BuildingInput", key: str, mat_name: str, recipe: str, params: dict):
    """Per-building material (so recolouring one building leaves the others alone) with the asked colours."""
    params = dict(params)
    colour = {"wall": v.wall_color, "brick": v.accent_color, "roof": v.roof_color, "frame": v.frame_color,
              "stairs": v.frame_color, "glass": v.glass_color}.get(key)
    if key == "roof" and v.roof in ("gable", "hip"):
        recipe, params = "paint", {"color": PITCHED_ROOF_COLOR, "roughness": 0.75}
    if colour is not None:
        if recipe == "wood_grain":
            params = {"light": colour, "dark": [c * 0.45 for c in colour[:3]] + [1.0]}
        else:
            params["color"] = colour
    return f"{v.name}_{mat_name[4:] if mat_name.startswith('bld_') else mat_name}", recipe, params


def _footprint(blocks, loc, yaw):
    xs, ys = [], []
    for x0, x1, y0, y1 in blocks:
        for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            wx, wy = _world(loc, yaw, p)
            xs.append(wx)
            ys.append(wy)
    return {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)]}


def _material(bridge, name: str, recipe: str, params: dict, fresh: bool = False) -> Optional[str]:
    """`fresh`: build it again with these params even if it exists (a rebuilt building gets its new colours)."""
    try:
        existing = bridge.get_material(name) if hasattr(bridge, "get_material") and not fresh else None
        if existing is not None:
            return getattr(existing, "name", name)
    except Exception:  # noqa: BLE001
        pass
    from .field_markings import _paint
    return _paint(bridge, name, recipe, params)
