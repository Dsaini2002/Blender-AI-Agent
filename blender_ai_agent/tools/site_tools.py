"""Site and finishing tools: 3D text (sign boards), a compound wall with a gate and security cabin, putting objects
into the collections the user asked for, and saving the .blend file."""

import fnmatch
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import Permission, Tool, ToolResult
from .building import BUCKETS, Mesher, _material
from .models import _coerce_bool, _coerce_list, _coerce_number, _vec3


# ------------------------------------------------------------------ text.create
@dataclass
class TextCreateInput:
    text: str
    name: str = "text"
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    size: float = 1.0
    extrude: float = 0.05
    upright: bool = True
    face_towards: Optional[List[float]] = None
    yaw_degrees: float = 0.0
    align: str = "CENTER"
    color: Optional[List[float]] = None
    glow: bool = False

    def __post_init__(self):
        self.text = str(self.text or "").strip()
        if not self.text:
            raise ValueError("TextCreateInput.text must be the words to show")
        self.text = self.text[:200]
        self.name = str(self.name or "text").strip() or "text"
        self.location = _vec3(self.location, "TextCreateInput.location")
        self.size = _coerce_number(self.size, "TextCreateInput.size")
        if not (0.01 <= self.size <= 50.0):
            raise ValueError("TextCreateInput.size (letter height in metres) must be 0.01-50")
        self.extrude = max(0.0, min(5.0, _coerce_number(self.extrude, "TextCreateInput.extrude")))
        self.upright = _coerce_bool(self.upright, "TextCreateInput.upright")
        self.glow = _coerce_bool(self.glow, "TextCreateInput.glow")
        self.yaw_degrees = _coerce_number(self.yaw_degrees, "TextCreateInput.yaw_degrees")
        if self.face_towards is not None:
            target = _coerce_list(self.face_towards, "TextCreateInput.face_towards")
            if len(target) not in (2, 3):
                raise ValueError("TextCreateInput.face_towards must be [x, y]")
            self.face_towards = target[:2]
        if self.color is not None:
            color = _coerce_list(self.color, "TextCreateInput.color")
            self.color = (list(color) + [1.0])[:4] if len(color) == 3 else list(color)[:4]


class TextCreateTool(Tool):
    name = "text.create"
    auto_name = "text"
    description = (
        "Creates 3D text (sign boards, name plates, logos in letters, labels). text = the words; size = letter "
        "height in metres; extrude = thickness; upright=true stands it up like a sign (default) - face_towards "
        "[x, y] turns its readable side to a point (e.g. the camera or the road); color [r,g,b]; glow=true for a "
        "lit sign. Put it on the face of a wall / board, 2-3 cm in front of it."
    )
    permission = Permission.SAFE_WRITE
    input_model = TextCreateInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: TextCreateInput) -> ToolResult:
        if not hasattr(self._bridge, "create_text"):
            return ToolResult.fail("3D text is not available on this bridge", code="UNSUPPORTED")
        yaw = math.radians(v.yaw_degrees)
        if v.face_towards is not None:
            dx, dy = v.face_towards[0] - v.location[0], v.face_towards[1] - v.location[1]
            if abs(dx) + abs(dy) > 1e-6:
                yaw = math.atan2(dy, dx) - math.atan2(-1.0, 0.0)          # readable side is -Y before turning
        rotation = [math.pi / 2.0 if v.upright else 0.0, 0.0, yaw]
        obj = self._bridge.create_text(name=v.name, body=v.text, location=list(v.location), rotation=rotation,
                                       size=v.size, extrude=v.extrude, align=v.align)
        name = getattr(obj, "name", v.name)
        color = v.color or ([1.0, 0.85, 0.5, 1.0] if v.glow else [0.95, 0.95, 0.95, 1.0])
        recipe, params = ("glow", {"color": color, "strength": 6.0}) if v.glow else \
            ("paint", {"color": color, "roughness": 0.35})
        mat = _material(self._bridge, f"{name}_mat", recipe, params)
        if mat:
            self._bridge.assign_material(name, mat)
        width = round(len(v.text) * v.size * 0.6, 2)
        return ToolResult.ok({"name": name, "text": v.text, "location": list(v.location), "size": v.size,
                              "approx_width_m": width, "yaw_degrees": round(math.degrees(yaw), 1)})


# ------------------------------------------------------------------ scene.organize
DEFAULT_COLLECTIONS = ("Buildings", "Rooms", "Furniture", "Courtyard", "Sports", "Landscaping", "Lighting", "Cameras")
AUTO_WORDS = {
    "building": r"building|hostel|block|structure|wall|glass|metal|door|stair|brick|sign|roof|window|facade|tower",
    "room": r"rooms?\b|partition|interior",
    "furniture": r"furniture|bed|desk|chair|table|fan|wardrobe|sofa|shelf|counter|tt_|bench_set|cabinet|stool",
    "courtyard": r"courtyard|garden|fountain|plaza|flower|planter|lawn|pond",
    "sport": r"court|net\b|_net|hoop|goal|field|pitch|basket|badminton|tennis|volley|cricket|grandstand|stand\b|racket|shuttle",
    "landscap": r"tree|bush|hedge|grass|ground|terrain|rock|palm|pine|path|road|walkway|bench|bicycle|bike|cycle|lamp|"
                r"boundary|gate|cabin|fence|campus_wall|compound|perimeter",
    "light": r"light|lamp|sun\b|sun_|spot",
    "camera": r"camera|cam\b|cam_",
}


@dataclass
class SceneOrganizeInput:
    collections: Any = None
    auto: bool = True
    defaulted: bool = False

    def __post_init__(self):
        value = self.collections
        if isinstance(value, str):
            value = [v.strip() for v in re.split(r"[,;\n]", value) if v.strip()]
        if isinstance(value, list):
            value = {str(v).strip(): [] for v in value if str(v).strip()}
        if value is None or value == {} or value == []:
            value = {name: [] for name in DEFAULT_COLLECTIONS}        # "organise the scene" with no names given
            self.defaulted = True
        if not isinstance(value, dict) or not value:
            raise ValueError("SceneOrganizeInput.collections must be {\"Collection\": [\"name\", \"prefix*\"]} or a "
                             "list of collection names")
        self.collections = {str(k).strip(): ([p] if isinstance(p, str) else [str(x) for x in (p or [])])
                            for k, p in value.items() if str(k).strip()}
        self.auto = _coerce_bool(self.auto, "SceneOrganizeInput.auto")


def _auto_key(collection: str) -> Optional[str]:
    low = collection.lower()
    for key in AUTO_WORDS:
        if key in low:
            return key
    if "landscape" in low or "nature" in low or "outdoor" in low:
        return "landscap"
    if "build" in low or "architect" in low:
        return "building"
    return None


def _literal_length(pattern: str) -> int:
    return len(pattern.replace("*", "").replace("?", ""))


class SceneOrganizeTool(Tool):
    name = "scene.organize"
    description = (
        "Puts objects into named collections (the Outliner folders the user asked for). collections = "
        "{\"Hostel_Building\": [\"hostel_*\"], \"Furniture\": [\"*_furniture*\", \"bed*\"], ...} with exact names "
        "or * patterns, or just a list of collection names - then objects are sorted by what their names / types "
        "say (lights -> a Lighting collection, cameras -> Cameras, trees / paths -> Landscaping, courts / nets -> "
        "Sports, beds / desks -> Furniture ...). Every object ends up in exactly one of them."
    )
    permission = Permission.SAFE_WRITE
    input_model = SceneOrganizeInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: SceneOrganizeInput) -> ToolResult:
        if not hasattr(self._bridge, "move_to_collection"):
            return ToolResult.fail("collections are not available on this bridge", code="UNSUPPORTED")
        objects = list(self._bridge.get_objects() or [])
        assigned: Dict[str, List[str]] = {c: [] for c in v.collections}
        taken = set()
        wanted = {c.lower(): c for c in v.collections}
        for obj in objects:                    # already in one of the asked-for collections (mesh.building does that)
            name = getattr(obj, "name", "")
            for coll in getattr(obj, "users_collection", None) or []:
                target = wanted.get(str(getattr(coll, "name", "")).lower())
                if target is not None:
                    exact = any(name.lower() == p.lower() for c, ps in v.collections.items() if c != target for p in ps)
                    if not exact:
                        assigned[target].append(name)
                        taken.add(name)
                    break
        for obj in objects:                     # explicit names / patterns: the most specific pattern wins
            name = getattr(obj, "name", "")
            if name in taken:
                continue
            best, best_len = None, -1
            for collection, patterns in v.collections.items():
                for p in patterns:
                    if name.lower() == p.lower():
                        length = 10_000
                    elif fnmatch.fnmatch(name.lower(), p.lower()):
                        length = _literal_length(p)
                    else:
                        continue
                    if length > best_len:
                        best, best_len = collection, length
            if best is not None:
                assigned[best].append(name)
                taken.add(name)
        if v.auto:
            keys = {c: _auto_key(c) for c in v.collections}
            for obj in objects:
                name = getattr(obj, "name", "")
                if name in taken:
                    continue
                kind = str(getattr(obj, "type", "") or "").upper()
                target = None
                if kind == "CAMERA":
                    target = next((c for c, k in keys.items() if k == "camera"), None)
                elif kind == "LIGHT":
                    target = next((c for c, k in keys.items() if k == "light"), None)
                if target is None:
                    low = name.lower()
                    by_kind = {k: c for c, k in reversed(list(keys.items())) if k}
                    # specific kinds first: 'hostel_furniture_wood' is furniture, not the building
                    for k in ("furniture", "room", "sport", "courtyard", "light", "landscap", "building"):
                        c = by_kind.get(k)
                        if c is None or not re.search(AUTO_WORDS[k], low):
                            continue
                        if k == "light" and kind not in ("LIGHT", ""):
                            continue
                        target = c
                        break
                if target is not None:
                    assigned[target].append(name)
                    taken.add(name)
        moved = {}
        for collection, names in assigned.items():
            if not names and v.defaulted:
                continue                       # no empty folders the user never named
            result = self._bridge.move_to_collection(names, collection)
            moved[collection] = len(result.get("moved", names)) if isinstance(result, dict) else len(names)
        left = [getattr(o, "name", "") for o in objects if getattr(o, "name", "") not in taken]
        return ToolResult.ok({"collections": moved, "not_sorted": left[:30],
                              "note": "Objects in not_sorted stayed where they were - add patterns for them if needed."})


# ------------------------------------------------------------------ scene.save
@dataclass
class SceneSaveInput:
    filename: str = ""
    filepath: str = ""

    def __post_init__(self):
        name = str(self.filepath or self.filename or "").strip().strip('"')
        if not name:
            raise ValueError("SceneSaveInput.filename is required, e.g. \"My_Scene.blend\"")
        if not name.lower().endswith(".blend"):
            name += ".blend"
        self.filename = name


LAST_SAVE: Dict[str, Any] = {}      # the last verified scene.save (the final save of a run writes there again)


def verify_saved_file(path: str, started: float = 0.0) -> str:
    """'' when `path` is a real, freshly written .blend; otherwise what is wrong."""
    if not path or not os.path.isfile(path):
        return f"no file at {path}"
    size = os.path.getsize(path)
    if size < 1024:
        return f"the file is only {size} bytes"
    if started and os.path.getmtime(path) < started - 2:
        return "the file on disk is older than this save (it was not written)"
    try:
        with open(path, "rb") as handle:
            head = handle.read(12)
    except OSError as exc:
        return f"cannot read it back: {exc}"
    if not (head.startswith(b"BLENDER") or head[:2] == b"\x1f\x8b" or head[:4] == b"\x28\xb5\x2f\xfd"):
        return "it is not a .blend file"
    return ""


def default_save_folder() -> str:
    return os.environ.get("BLENDER_AI_SAVE_DIR") or os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "scenes")


class SceneSaveTool(Tool):
    name = "scene.save"
    description = (
        "Saves the scene as a .blend file. filename = e.g. \"IIT_Hostel_Campus.blend\" (saved next to the current "
        "file, or in ~/BlenderAIAgent/scenes when the file was never saved). Use it only when the user asks to save."
    )
    permission = Permission.SAFE_WRITE
    input_model = SceneSaveInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: SceneSaveInput) -> ToolResult:
        if not hasattr(self._bridge, "save_blend"):
            return ToolResult.fail("saving is not available on this bridge", code="UNSUPPORTED")
        path = os.path.expanduser(v.filename)
        if not os.path.isabs(path):
            current = ""
            try:
                current = self._bridge.current_blend_path() if hasattr(self._bridge, "current_blend_path") else ""
            except Exception:  # noqa: BLE001
                current = ""
            folder = os.path.dirname(current) if current else default_save_folder()
            path = os.path.join(folder, os.path.basename(path))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        import time as _time
        started = _time.time()
        result = self._bridge.save_blend(path)
        saved = (result or {}).get("filepath") or path
        problem = verify_saved_file(saved, started)
        if problem:
            return ToolResult.fail(f"scene.save did not write a usable file: {problem}")
        LAST_SAVE.update(filename=v.filename, filepath=saved, time=_time.time(), bytes=os.path.getsize(saved))
        return ToolResult.ok({"filepath": saved, "bytes": os.path.getsize(saved), "verified": True,
                              "note": "Saved and checked on disk. Ctrl+S in Blender saves further changes there."})


# ------------------------------------------------------------------ mesh.boundary_wall
WALL_BUCKETS = {"wall": "_wall", "brick": "_pillars", "metal": "_gate", "frame": "_coping", "glass": "_cabin_glass",
                "door": "_cabin_door"}


@dataclass
class BoundaryWallInput:
    name: str = "boundary"
    size: Optional[List[float]] = None
    around: Optional[List[float]] = None
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    height: float = 2.2
    thickness: float = 0.25
    pillar_every: float = 3.5
    gate: bool = True
    gate_side: str = "front"
    gate_width: float = 6.0
    gate_offset: float = 0.0
    cabin: bool = True
    sign_text: str = ""

    def __post_init__(self):
        self.name = str(self.name or "boundary").strip().replace(" ", "_") or "boundary"
        self.location = _vec3(self.location, "BoundaryWallInput.location")
        if self.around is not None:                       # [xmin, xmax, ymin, ymax] (+ margin) -> size & centre
            box = [float(x) for x in _coerce_list(self.around, "BoundaryWallInput.around")]
            if len(box) != 4:
                raise ValueError("BoundaryWallInput.around must be [xmin, xmax, ymin, ymax]")
            self.size = [box[1] - box[0], box[3] - box[2]]
            self.location = [(box[0] + box[1]) / 2.0, (box[2] + box[3]) / 2.0, self.location[2]]
        if self.size is None:
            raise ValueError("BoundaryWallInput.size [width, depth] (or around [xmin, xmax, ymin, ymax]) is required")
        size = _coerce_list(self.size, "BoundaryWallInput.size")
        if len(size) < 2 or not all(4.0 <= float(s) <= 2000.0 for s in size[:2]):
            raise ValueError("BoundaryWallInput.size must be [width, depth], each 4-2000 m")
        self.size = [float(size[0]), float(size[1])]
        for attr, lo, hi in (("height", 0.5, 6.0), ("thickness", 0.1, 1.0), ("pillar_every", 1.5, 20.0),
                             ("gate_width", 1.0, 20.0)):
            value = _coerce_number(getattr(self, attr), f"BoundaryWallInput.{attr}")
            if not (lo <= value <= hi):
                raise ValueError(f"BoundaryWallInput.{attr} must be {lo}-{hi}")
            setattr(self, attr, value)
        self.gate_offset = _coerce_number(self.gate_offset, "BoundaryWallInput.gate_offset")
        self.gate = _coerce_bool(self.gate, "BoundaryWallInput.gate")
        self.cabin = _coerce_bool(self.cabin, "BoundaryWallInput.cabin")
        self.sign_text = str(self.sign_text or "").strip()[:40]
        side = str(self.gate_side or "front").strip().lower()
        side = {"south": "front", "-y": "front", "north": "back", "+y": "back", "west": "left", "-x": "left",
                "east": "right", "+x": "right"}.get(side, side)
        if side not in ("front", "back", "left", "right"):
            raise ValueError("BoundaryWallInput.gate_side must be front (-Y), back (+Y), left (-X) or right (+X)")
        self.gate_side = side


def boundary_mesh(v: BoundaryWallInput):
    """Local frame centred on the enclosure; returns (Mesher, gate centre local, inward normal)."""
    m = Mesher()
    hx, hy = v.size[0] / 2.0, v.size[1] / 2.0
    t, h = v.thickness, v.height
    sides = {"front": ((-hx, -hy), (hx, -hy), (0.0, 1.0)), "back": ((hx, hy), (-hx, hy), (0.0, -1.0)),
             "left": ((-hx, hy), (-hx, -hy), (1.0, 0.0)), "right": ((hx, -hy), (hx, hy), (-1.0, 0.0))}
    gate_centre, inward = None, (0.0, 1.0)
    for side, (a, b, n) in sides.items():
        length = math.hypot(b[0] - a[0], b[1] - a[1])
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        gaps = []
        if v.gate and side == v.gate_side:
            mid = length / 2.0 + v.gate_offset
            gaps.append((mid - v.gate_width / 2.0, mid + v.gate_width / 2.0))
            gate_centre = (a[0] + ux * mid, a[1] + uy * mid)
            inward = n

        def seg(u0, u1, z0, z1, key, grow=0.0):
            x0, y0 = a[0] + ux * u0, a[1] + uy * u0
            x1, y1 = a[0] + ux * u1, a[1] + uy * u1
            half = t / 2.0 + grow
            m.box(key, min(x0, x1) - (half if uy else 0), max(x0, x1) + (half if uy else 0),
                  min(y0, y1) - (half if ux else 0), max(y0, y1) + (half if ux else 0), z0, z1)

        cuts = [(0.0, length)]
        for g0, g1 in gaps:
            cuts = [(s, min(e, g0)) for s, e in cuts if s < g0] + [(max(s, g1), e) for s, e in cuts if e > g1]
        for s, e in cuts:
            if e - s < 0.05:
                continue
            seg(s, e, 0.0, h, "wall")
            seg(s, e, h, h + 0.08, "frame", grow=0.05)                       # coping
            n_p = max(1, int((e - s) / v.pillar_every))
            for i in range(n_p + 1):
                u = s + (e - s) * i / n_p
                seg(max(s, u - 0.22), min(e, u + 0.22), 0.0, h + 0.25, "brick", grow=0.08)
        for g0, g1 in gaps:                                                    # gate pillars + gate leaves
            for u in (g0 - 0.4, g1 + 0.4):
                seg(u - 0.4, u + 0.4, 0.0, h + 0.9, "brick", grow=0.15)
                seg(u - 0.45, u + 0.45, h + 0.9, h + 1.0, "frame", grow=0.2)
            if v.sign_text:                                                # name arch over the gate
                arch_z = h + 2.2
                for u in (g0 - 0.4, g1 + 0.4):
                    seg(u - 0.25, u + 0.25, h + 1.0, arch_z, "brick", grow=0.05)
                seg(g0 - 0.9, g1 + 0.9, arch_z, arch_z + 1.0, "frame", grow=0.1)
            gh = min(h + 0.2, 2.4)
            bars = max(4, int((g1 - g0) / 0.15))
            for i in range(bars + 1):
                u = g0 + (g1 - g0) * i / bars
                seg(u - 0.02, u + 0.02, 0.05, gh, "metal", grow=-t / 2.0 + 0.03)
            for z in (0.1, gh / 2.0, gh - 0.06):
                seg(g0, g1, z, z + 0.06, "metal", grow=-t / 2.0 + 0.04)
    if v.gate and v.cabin and gate_centre is not None:                        # security cabin just inside the gate
        nx, ny = inward
        ux, uy = ny, -nx
        cx = gate_centre[0] + nx * 3.2 + ux * (v.gate_width / 2.0 + 2.6)
        cy = gate_centre[1] + ny * 3.2 + uy * (v.gate_width / 2.0 + 2.6)
        s, ch = 1.5, 2.7
        m.box("wall", cx - s, cx + s, cy - s, cy - s + 0.2, 0.0, ch)
        m.box("wall", cx - s, cx + s, cy + s - 0.2, cy + s, 0.0, ch)
        m.box("wall", cx - s, cx - s + 0.2, cy - s, cy + s, 0.0, ch)
        m.box("wall", cx + s - 0.2, cx + s, cy - s, cy + s, 0.0, ch)
        m.box("frame", cx - s - 0.4, cx + s + 0.4, cy - s - 0.4, cy + s + 0.4, ch, ch + 0.2)
        m.box("frame", cx - s, cx + s, cy - s, cy + s, 0.0, 0.1)
        # windows on all four sides (glass in front of the wall) and a door facing inwards
        for (wx, wy, along_x) in ((cx, cy - s - 0.01, True), (cx, cy + s + 0.01, True),
                                  (cx - s - 0.01, cy, False), (cx + s + 0.01, cy, False)):
            if along_x:
                m.box("glass", wx - 0.8, wx + 0.8, wy - 0.02, wy + 0.02, 1.0, 2.1)
            else:
                m.box("glass", wx - 0.02, wx + 0.02, wy - 0.8, wy + 0.8, 1.0, 2.1)
        dx, dy = cx + nx * (s + 0.02), cy + ny * (s + 0.02)            # door on the side facing the site
        if abs(nx) > 0.5:
            m.box("door", dx - 0.03, dx + 0.03, dy - 0.45, dy + 0.45, 0.0, 2.05)
        else:
            m.box("door", dx - 0.45, dx + 0.45, dy - 0.03, dy + 0.03, 0.0, 2.05)
        # boom barrier across the gate, inside
        bx, by = gate_centre[0] + nx * 1.5 - ux * (v.gate_width / 2.0 - 0.2), gate_centre[1] + ny * 1.5 - uy * (v.gate_width / 2.0 - 0.2)
        m.box("brick", bx - 0.25, bx + 0.25, by - 0.25, by + 0.25, 0.0, 1.0)
        ex, ey = bx + ux * (v.gate_width - 0.4), by + uy * (v.gate_width - 0.4)
        m.box("metal", min(bx, ex) - 0.05, max(bx, ex) + 0.05, min(by, ey) - 0.05, max(by, ey) + 0.05, 0.95, 1.05)
    return m, gate_centre, inward


class MeshBoundaryWallTool(Tool):
    name = "mesh.boundary_wall"
    description = (
        "Builds a compound / boundary wall around a site in one call: plastered wall with brick pillars every "
        "pillar_every metres and a coping on top, a main gate (two brick gate posts + steel bar gate) on gate_side "
        "(front = -Y, back, left, right), a security cabin with windows just inside the gate and a boom barrier; sign_text puts a name arch with "
        "letters over the gate (use it for the campus name - never a floating text.create there). "
        "size = [width, depth] of the enclosure centred on location, or around = [xmin, xmax, ymin, ymax] (e.g. the "
        "building footprint plus 15-25 m for courts and parking). Returns the gate position for the entry road."
    )
    permission = Permission.SAFE_WRITE
    input_model = BoundaryWallInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: BoundaryWallInput) -> ToolResult:
        m, gate, inward = boundary_mesh(v)
        recipes = {"wall": ("bld_boundary_wall", "paint", {"color": [0.86, 0.8, 0.68, 1.0], "roughness": 0.8})}
        created = []
        for key, suffix in WALL_BUCKETS.items():
            if not m.boxes.get(key):
                continue
            verts, faces = m.mesh(key)
            obj = self._bridge.create_mesh(name=f"{v.name}{suffix}", vertices=verts, faces=faces,
                                           location=list(v.location), rotation=[0.0, 0.0, 0.0], scale=[1.0, 1.0, 1.0])
            name = getattr(obj, "name", f"{v.name}{suffix}")
            _suffix, mat_name, recipe, params, _role = BUCKETS[key]
            mat_name, recipe, params = recipes.get(key, (mat_name, recipe, params))
            mat = _material(self._bridge, mat_name, recipe, params)
            if mat:
                self._bridge.assign_material(name, mat)
            created.append(name)
        lx, ly, _lz = v.location
        result = {"objects": created, "size": v.size, "centre": [lx, ly],
                  "inside": {"x": [lx - v.size[0] / 2.0, lx + v.size[0] / 2.0],
                             "y": [ly - v.size[1] / 2.0, ly + v.size[1] / 2.0]}}
        if gate is not None and v.sign_text and hasattr(self._bridge, "create_text"):
            nx, ny = inward                                                 # letters on the outer face of the arch
            arch_mid = v.height + 2.7
            out = v.thickness / 2.0 + 0.12
            size = min(0.75, (v.gate_width + 1.4) / max(len(v.sign_text) * 0.62, 1.0))
            yaw = math.atan2(-ny, -nx) - math.atan2(-1.0, 0.0)
            sign = self._bridge.create_text(name=f"{v.name}_gate_sign", body=v.sign_text,
                                            location=[lx + gate[0] - nx * out, ly + gate[1] - ny * out, arch_mid - size * 0.35],
                                            rotation=[math.pi / 2.0, 0.0, yaw], size=size, extrude=0.03, align="CENTER")
            sign_name = getattr(sign, "name", f"{v.name}_gate_sign")
            mat = _material(self._bridge, "bld_gate_sign", "paint", {"color": [0.08, 0.15, 0.45, 1.0], "roughness": 0.4})
            if mat:
                self._bridge.assign_material(sign_name, mat)
            created.append(sign_name)
        if gate is not None:
            result["gate"] = [round(lx + gate[0], 2), round(ly + gate[1], 2)]
            result["road_inwards"] = [round(inward[0], 2), round(inward[1], 2)]
            result["note"] = "Run the entry road / main path from the gate inwards (road_inwards) to the building."
        return ToolResult.ok(result)
