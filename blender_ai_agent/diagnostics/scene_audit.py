"""Error finder: reads the scene and writes EVERY problem it can measure into errors.txt. It changes nothing.

It works on a read-only snapshot (bridge.scene_snapshot()) so it can run any time - after a build, inside every
automatic-check round, or from the panel's "Find Errors" button - and on fake data in tests.

What it looks for (each finding says which objects, the measured numbers, why it is wrong and how to fix it):
  OVERLAP       two things in the same space (desk inside a bookshelf), furniture through a wall / floor
  FLOATING      standing things with nothing under them
  SUNK          things below the floor
  OUTSIDE ROOM  furniture outside the walls of a room
  CAMERA        no camera, camera not active, objects the camera does not see at all
  LIGHTS        lights stacked on one spot, lights with no energy, lights buried inside objects
  MATERIAL      visible objects without a material
  SIZE / SCALE  zero / negative / extreme scale, things far too big or too small for what their name says
  TILTED        furniture leaning (rotated about X or Y)
  DUPLICATE     two identical objects in the same place
  DEFAULT       Blender's default cube / primitives left as they are
  COLLECTIONS   empty collections, objects outside the asked collections
  MISSING?      things the request names that no object name mentions
"""

import json
import math
import os
import re
import time
from typing import Dict, List, Optional

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}

STRUCTURE = re.compile(r"wall|floor|ceiling|roof|ground|terrain|plane|slab|base_plate|foundation|lawn|grass_?field",
                       re.IGNORECASE)
WALL = re.compile(r"wall|partition", re.IGNORECASE)
FLOOR = re.compile(r"floor|ground|terrain|lawn|slab|plane", re.IGNORECASE)
HANGS = re.compile(r"ceiling|pendant|chandelier|fan|lamp_shade|light|led|strip|shelf|shelves|wall_art|art|painting|"
                   r"picture|frame|poster|mirror|clock|curtain|rod|window|glass|whiteboard|board|sign|tv_screen|"
                   r"cloud|sky|sun|bird|canopy|roof|beam|cable|wire|rope|monitor|screen|panel|vent|ac_unit", re.IGNORECASE)
CONTENTS = re.compile(r"book|novel|magazine|file|folder|cushion|pillow|blanket|duvet|sheet|mattress|throw|"
                      r"keyboard|mouse|monitor|screen|laptop|lamp|cup|mug|vase|plant|pot|soil|leaves|leaf|bulb|"
                      r"drawer|handle|knob|door_line|glass|frame|candle|crystal|tray|plate|bottle|decor", re.IGNORECASE)
ON_WALL = re.compile(r"whiteboard|blackboard|painting|wall_art|poster|mirror|clock|tv_screen|wall_panel|"
                     r"wall_shelf|floating_shel|picture|photo_frame|notice_board", re.IGNORECASE)
GROUP_WORDS = re.compile(r"parking|rack|row|set\b|_set|group|stand|area|zone|lot|stack|collection|"
                         r"(chair|table|desk|door|window|lamp|light|tree|bench|car|book|plant|bicycle|cup)s\b", re.IGNORECASE)
GENERIC = re.compile(r"^(prism_object|mesh_object|object|obj|mesh|shape|part|new_object|item|empty|cube_object|"
                     r"lathe_object|curve_object|sdf_object|text_object)(\.\d+|_\d+)?$", re.IGNORECASE)
GLASSY = re.compile(r"glass|window|mirror|screen|whiteboard|board|wall_art|painting|poster|frame", re.IGNORECASE)
FLAT_KINDS = re.compile(r"whiteboard|blackboard|painting|poster|mirror|tv_screen|window|door|rug|carpet|wall_art|"
                        r"notice_board|picture", re.IGNORECASE)
ROOM_WALL = re.compile(r"(^|_)walls?((_(back|front|left|right|north|south|east|west|side|rear|main|plus|minus|pos|neg|"
                       r"[xy]|\d+))*)$", re.IGNORECASE)   # 'room_back_wall', 'wall_left', 'wall_back_plus_y' - not 'wall_gate'
STARTUP_LIGHT = (4.08, 1.01, 5.90)
STARTUP_CAMERA = (7.36, -6.93, 4.96)
TUCK = re.compile(r"chair|stool|seat|bench|ottoman", re.IGNORECASE)
TABLE = re.compile(r"table|desk|counter|bar", re.IGNORECASE)
RUG = re.compile(r"rug|carpet|mat\b|mat_|dari", re.IGNORECASE)
DEFAULT_NAMES = re.compile(r"^(Cube|Sphere|Cylinder|Cone|Torus|Plane|Circle|Icosphere|Suzanne|Monkey)(\.\d+)?$")

# real sizes (tallest side, metres) for the things people ask for most - far outside = wrong size
TYPICAL_SIZE = {
    "chair": (0.6, 1.3), "desk": (0.6, 2.4), "table": (0.4, 3.2), "bed": (1.7, 2.6), "sofa": (1.2, 3.2),
    "bookshelf": (0.8, 3.0), "wardrobe": (1.0, 2.6), "door": (1.8, 2.8), "window": (0.5, 3.5), "lamp": (0.2, 2.2),
    "monitor": (0.3, 0.9), "keyboard": (0.3, 0.6), "mouse": (0.05, 0.15), "plant": (0.2, 2.5), "rug": (0.8, 4.0),
    "whiteboard": (0.6, 2.5), "car": (3.0, 6.0), "bench": (1.0, 2.5), "tree": (2.0, 30.0), "person": (1.4, 2.1),
    "cup": (0.06, 0.2), "book": (0.1, 0.4), "tv": (0.6, 2.2), "fan": (0.3, 1.6), "bicycle": (1.4, 2.0),
}

REQUEST_WORDS = [
    "window", "door", "desk", "chair", "bookshelf", "shelf", "lamp", "monitor", "keyboard", "mouse", "plant",
    "whiteboard", "sofa", "bed", "table", "rug", "carpet", "curtain", "tv", "television", "cabinet", "wardrobe",
    "light", "led", "panel", "ceiling", "floor", "wall", "book", "mirror", "fan", "camera", "painting", "frame",
    "clock", "pillow", "nightstand", "chandelier", "pool", "tree", "bench", "gate", "fence", "path", "car", "road",
    "stairs", "staircase", "balcony", "roof", "kitchen", "fridge", "stove", "sink", "toilet", "bathtub", "shower",
    "laptop", "computer", "printer", "vase", "sign", "court", "net", "goal", "hoop", "bicycle", "parking", "garden",
]
SYNONYMS = {"bookshelf": ["shelf", "bookcase"], "tv": ["television", "tv_unit"], "carpet": ["rug"], "rug": ["carpet"],
            "light": ["lamp", "led", "sun", "chandelier", "pendant"], "plant": ["bush", "tree", "pot"],
            "stairs": ["stair", "step"], "staircase": ["stair"], "computer": ["monitor", "pc"],
            "painting": ["wall_art", "art", "picture", "frame"], "sofa": ["couch", "armchair"]}


# ---------------------------------------------------------------- small helpers
def _overlap(a: dict, b: dict) -> List[float]:
    return [min(a["max"][k], b["max"][k]) - max(a["min"][k], b["min"][k]) for k in range(3)]


def _size(box: dict) -> List[float]:
    return [box["max"][k] - box["min"][k] for k in range(3)]


def _volume(box: dict) -> float:
    s = _size(box)
    return max(1e-9, s[0] * s[1] * max(s[2], 1e-3))


def _union(boxes: List[dict]) -> dict:
    return {"min": [min(b["min"][k] for b in boxes) for k in range(3)],
            "max": [max(b["max"][k] for b in boxes) for k in range(3)]}


def _fmt(v) -> str:
    return "[" + ", ".join(f"{c:.2f}" for c in v) + "]"


def _library_parts() -> Dict[str, List[str]]:
    try:
        from ..tools.library_tools import load_library
        return {name: [p["name"] for p in spec.get("parts", [])] + [l["name"] for l in spec.get("lights", [])]
                for name, spec in load_library().items()}
    except Exception:  # noqa: BLE001
        return {}


def group_items(names: List[str], parts_by_model: Dict[str, List[str]]) -> Dict[str, dict]:
    """Objects -> things: a library model is many objects ('study_desk_desk', 'bookshelf_shelf.002' ...) - whatever
    prefix the agent gave it. Returns {item: {"objects": [...], "model": name or ""}}."""
    items: Dict[str, dict] = {}
    part_index = sorted(((p, m) for m, ps in parts_by_model.items() for p in ps), key=lambda pm: -len(pm[0]))
    for name in names:
        base, dot, copy = name.partition(".")
        copy = dot + copy if copy.isdigit() else ""
        found = None
        if STRUCTURE.search(base) and not any(base.startswith(m + "_") for m in parts_by_model):
            part_index_here = []          # a wall / floor the agent made itself is its own thing
        else:
            part_index_here = part_index
        for part, model in part_index_here:
            if base.endswith("_" + part) and len(base) > len(part) + 1:
                prefix = base[: -len(part) - 1]
                found = (prefix + copy, model)
                break
        if found is None:
            found = (name, "")
        entry = items.setdefault(found[0], {"objects": [], "models": {}})
        entry["objects"].append(name)
        if found[1]:
            entry["models"][found[1]] = entry["models"].get(found[1], 0) + 1
    out = {}
    for key, entry in items.items():
        model = max(entry["models"], key=entry["models"].get) if entry["models"] else ""
        # one object that only *looks* like a part (e.g. a lone 'room_frame') stays itself
        if model and len(entry["objects"]) == 1 and len(parts_by_model.get(model, [])) > 2 \
                and not key.startswith(model):
            out[entry["objects"][0]] = {"objects": entry["objects"], "model": ""}
            continue
        out[key] = {"objects": entry["objects"], "model": model}
    return out


def _kind(name: str) -> str:
    low = name.lower()
    for word in sorted(TYPICAL_SIZE, key=len, reverse=True):
        if word in low:
            return word
    return ""


# ---------------------------------------------------------------- the checks
class Finder:

    def __init__(self, snapshot: dict, request: str = "", console: str = ""):
        self.snapshot = snapshot
        self.request = request or ""
        self.console = console or ""
        self.findings: List[dict] = []
        self._on_zero: List[str] = []
        self._swallowers = set()
        objects = [o for o in snapshot.get("objects", []) if not o.get("hidden")]
        self.objects = {o["name"]: o for o in objects}
        self.solid = {n: o for n, o in self.objects.items() if o.get("box") and o["type"] in
                      ("MESH", "CURVE", "SURFACE", "META", "FONT")}
        library = _library_parts()
        self.library = library
        self.items = group_items(sorted(self.solid), library)
        self.item_box = {k: _union([self.solid[n]["box"] for n in v["objects"]]) for k, v in self.items.items()}
        self._merge_buildings()
        self.structure = {k for k in self.items if STRUCTURE.search(k) and not self.items[k]["model"]}
        self.walls = {k for k in self.structure if WALL.search(k) and min(_size(self.item_box[k])[:2]) <= 0.8}
        self.shape_walls = set()
        for k, b in self.item_box.items():   # a thin, long, tall slab is a wall whatever it is called ('prism_object')
            size = _size(b)
            if not self.items[k]["model"] and k not in self.structure and min(size[:2]) <= 0.35 \
                    and max(size[:2]) >= 2.0 and size[2] >= 2.0 and not self._glassy(k):
                self.shape_walls.add(k)
        self.structure |= self.shape_walls
        self.walls |= self.shape_walls
        floors = [k for k in self.structure if FLOOR.search(k) and _size(self.item_box[k])[2] <= 0.5]
        self.floor_z = max((self.item_box[k]["max"][2] for k in floors), default=0.0)

    def _merge_buildings(self):
        """A generated building is joined per material ('hostel_brick', 'hostel_glass', 'hostel_doors' ...): those
        pieces all fill the same big box on purpose. They are one thing ('hostel'), not 20 clashes."""
        groups: Dict[str, List[str]] = {}
        for item, entry in self.items.items():
            if entry["model"] or "_" not in item:
                continue
            groups.setdefault(item.split("_", 1)[0], []).append(item)
        for prefix, members in groups.items():
            if len(members) < 3 or prefix in self.items:
                continue
            solid = [m for m in members if not STRUCTURE.search(m)]
            if not solid:
                continue          # only ground / walls (a campus boundary): nothing to merge
            biggest = max(solid, key=lambda m: max(_size(self.item_box[m])[:2]))
            big = self.item_box[biggest]
            if max(_size(big)[:2]) < 8.0:
                continue
            inside = []
            for m in members:
                b = self.item_box[m]
                centre = [(b["min"][k] + b["max"][k]) / 2.0 for k in range(3)]
                if all(big["min"][k] - 1.0 <= centre[k] <= big["max"][k] + 1.0 for k in range(3)):
                    inside.append(m)
            if len(inside) < 3:
                continue
            objects = [o for m in inside for o in self.items.pop(m)["objects"]]
            for m in inside:
                self.item_box.pop(m)
            self.items[prefix] = {"objects": objects, "model": "", "building": True}
            self.item_box[prefix] = _union([self.solid[n]["box"] for n in objects])

    def _materials(self, item: str) -> str:
        return " ".join(m for n in self.items.get(item, {}).get("objects", [item]) for m in
                        (self.objects.get(n, {}).get("materials") or []) if m)

    def _glassy(self, item: str) -> bool:
        return bool(GLASSY.search(item) or GLASSY.search(self._materials(item)))

    def add(self, severity, kind, objects, what, why, fix, numbers=None):
        self.findings.append({"severity": severity, "kind": kind, "objects": list(objects), "what": what,
                              "why": why, "fix": fix, "numbers": numbers or {}})

    def hangs(self, item: str) -> bool:
        model = self.items[item]["model"]
        if model:
            try:
                from ..tools.library_tools import load_library
                spec = load_library().get(model, {})
                if spec.get("hangs") or spec.get("category") in ("light", "sky"):
                    return True
            except Exception:  # noqa: BLE001
                pass
        return bool(HANGS.search(item) or self._glassy(item))

    def run(self) -> List[dict]:
        for step in (self.check_camera, self.check_overlaps, self.check_structure, self.check_support, self.check_wall_items,
                     self.check_room, self.check_lights, self.check_materials, self.check_scale, self.check_sizes,
                     self.check_tilt, self.check_duplicates, self.check_defaults, self.check_collections,
                     self.check_request, self.check_console, self.check_names, self.check_wall_shapes,
                     self.check_flat_things, self.check_startup_leftovers):
            try:
                step()
            except Exception as exc:  # noqa: BLE001 — one broken check must not hide the others
                self.add("low", "FINDER", [], f"the {step.__name__} check could not run", str(exc), "report this")
        self.findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 3), f["kind"]))
        return self.findings

    # -- camera
    def check_camera(self):
        cameras = [o for o in self.objects.values() if o["type"] == "CAMERA"]
        if not cameras:
            self.add("high", "CAMERA", [], "there is no camera", "nothing can be rendered", "camera.create")
            return
        if not self.snapshot.get("camera"):
            self.add("high", "CAMERA", [c["name"] for c in cameras], "no camera is active",
                     "renders use the active camera", f"camera.set(name='{cameras[0]['name']}')")
            return
        unseen, partly = [], []
        for item, box in self.item_box.items():
            if item in self.structure:
                continue
            views = [self.solid[n].get("in_view") for n in self.items[item]["objects"]]
            views = [v for v in views if v is not None]
            if not views:
                continue
            if max(views) == 0.0:
                unseen.append(item)
            elif max(views) < 0.5:
                partly.append(item)
        if unseen:
            self.add("high", "CAMERA", unseen, f"{len(unseen)} thing(s) are completely outside the camera view",
                     "they will not be in the render", "move the camera back / turn it, or use a wider lens (camera.create)")
        if partly:
            self.add("low", "CAMERA", partly, f"{len(partly)} thing(s) are only partly in the camera view",
                     "cut off at the image edge", "frame the camera so everything fits")

    # -- two things in one place
    def _allowed(self, a: str, b: str, ov: List[float]) -> Optional[str]:
        A, B = self.item_box[a], self.item_box[b]
        if ov[2] <= 0.03:
            return "resting on / under"
        if abs(A["min"][2] - B["max"][2]) <= 0.04 or abs(B["min"][2] - A["max"][2]) <= 0.04:
            return "standing on top"
        if (TUCK.search(a) and TABLE.search(b)) or (TUCK.search(b) and TABLE.search(a)):
            return "chair under a table"
        if RUG.search(a) or RUG.search(b):
            return "rug"
        small, big = (a, b) if _volume(A) < _volume(B) else (b, a)
        if CONTENTS.search(small) and _volume(self.item_box[small]) < 0.35 * _volume(self.item_box[big]):
            sb = self.item_box[small]
            bb = self.item_box[big]
            inside = all(sb["min"][k] >= bb["min"][k] - 0.03 and sb["max"][k] <= bb["max"][k] + 0.03 for k in range(3))
            if inside:
                return "small thing kept in / on it"
        return None

    def _same_box(self, a: str, b: str) -> bool:
        A, B = self.item_box[a], self.item_box[b]
        return all(abs(A[e][k] - B[e][k]) < 0.01 for e in ("min", "max") for k in range(3))

    def check_overlaps(self):
        names = [k for k in self.items if k not in self.structure]
        pairs = []
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                ov = _overlap(self.item_box[a], self.item_box[b])
                if min(ov[0], ov[1]) >= 0.03 and ov[2] >= 0.03 and not self._allowed(a, b, ov):
                    pairs.append((a, b))
        partners: Dict[str, List[str]] = {}
        for a, b in pairs:
            partners.setdefault(a, []).append(b)
            partners.setdefault(b, []).append(a)
        swallowers = set()
        for big, inner in partners.items():
            bigger = [o for o in inner if _volume(self.item_box[big]) > 3 * _volume(self.item_box[o])]
            if len(bigger) >= 3:
                swallowers.add(big)
                self._swallowers.add(big)
                size = _size(self.item_box[big])
                self.add("high", "OVERLAP", [big] + bigger,
                         f"'{big}' is a solid {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m block and {len(bigger)} "
                         f"things are inside it: {', '.join(bigger)}",
                         "one wrong object hides / swallows many others (e.g. the start-up Cube scaled into a 'room')",
                         f"delete '{big}' or give it its real size and place - then the others are free",
                         {"box": [[round(v, 2) for v in self.item_box[big]['min']], [round(v, 2) for v in self.item_box[big]['max']]]})
        for a, b in pairs:
            if a in swallowers or b in swallowers or self._same_box(a, b):
                continue
            if True:
                ov = _overlap(self.item_box[a], self.item_box[b])
                if min(ov[0], ov[1]) < 0.03 or ov[2] < 0.03:
                    continue
                if self._allowed(a, b, ov):
                    continue
                shared = max(0.0, ov[0]) * max(0.0, ov[1]) * max(0.0, ov[2])
                smaller = min(_volume(self.item_box[a]), _volume(self.item_box[b]))
                part = shared / smaller
                if part < 0.02:
                    continue
                severity = "high" if part >= 0.15 or min(ov[0], ov[1]) >= 0.1 else "medium"
                small, big = (a, b) if _volume(self.item_box[a]) <= _volume(self.item_box[b]) else (b, a)
                move = _push(self.item_box[big], self.item_box[small])
                self.add(severity, "OVERLAP", [small, big],
                         f"'{small}' and '{big}' are inside each other",
                         f"{ov[0]:.2f} x {ov[1]:.2f} x {ov[2]:.2f} m overlap = {part * 100:.0f}% of '{small}'",
                         f"object.move_by(names=['{small}'], offset={move}) (moves all its parts) or move '{big}'",
                         {"overlap_m": [round(v, 3) for v in ov], "share": round(part, 3),
                          "objects_" + small: self.items[small]["objects"][:8],
                          "objects_" + big: self.items[big]["objects"][:8]})

    # -- through walls / floor
    def check_structure(self):
        centre = self._room_centre()
        for item, box in self.item_box.items():
            if item in self.structure:
                continue
            for wall in self.walls:
                w = self.item_box[wall]
                ov = _overlap(box, w)
                if min(ov[0], ov[1]) < 0.04 or ov[2] < 0.1:
                    continue
                k = 0 if _size(w)[0] <= _size(w)[1] else 1
                mid = (w["min"][k] + w["max"][k]) / 2.0
                move = [0.0, 0.0, 0.0]
                move[k] = round((w["min"][k] - box["max"][k] - 0.02) if centre[k] < mid else (w["max"][k] - box["min"][k] + 0.02), 2)
                depth = (box["max"][k] - w["min"][k]) if centre[k] < mid else (w["max"][k] - box["min"][k])
                out = box["max"][k] > w["max"][k] + 0.01 if centre[k] < mid else box["min"][k] < w["min"][k] - 0.01
                beyond = (box["max"][k] - w["max"][k]) if centre[k] < mid else (w["min"][k] - box["min"][k])
                self.add("high" if depth >= 0.08 else "medium", "THROUGH WALL", [item, wall],
                         f"'{item}' goes {depth:.2f} m into the wall '{wall}'"
                         + (f" and sticks out {beyond:.2f} m on the OTHER side" if out else ""),
                         "furniture sticks through the wall (seen from outside too)",
                         f"object.move_by(names=['{item}'], offset={move})", {"depth_m": round(depth, 3)})
            if box["min"][2] < self.floor_z - 0.03 and not STRUCTURE.search(item) and item not in self._swallowers:
                depth = self.floor_z - box["min"][2]
                if abs(box["min"][2]) <= 0.01 and self.floor_z <= 0.1:
                    self._on_zero.append(item)
                    continue
                self.add("high" if depth > 0.1 else "medium", "SUNK", [item],
                         f"'{item}' goes {depth:.2f} m below the floor (floor top z={self.floor_z:.2f})",
                         "its legs / base are hidden in the floor",
                         f"object.move_by(names=['{item}'], offset=[0, 0, {depth:.2f}])", {"depth_m": round(depth, 3)})

        if self._on_zero:
            self.add("medium", "SUNK", self._on_zero,
                     f"{len(self._on_zero)} thing(s) stand at z=0 but the floor's top is at z={self.floor_z:.2f}, so "
                     f"their bottoms are {self.floor_z:.2f} m inside the floor",
                     "the floor slab was made centred on z=0 instead of having its top at z=0",
                     f"move the floor down by {self.floor_z:.2f} m (object.move_by(names=['<floor>'], "
                     f"offset=[0, 0, {-self.floor_z:.2f}]))", {"things": len(self._on_zero)})

    # -- floating
    def check_support(self):
        for item, box in self.item_box.items():
            if item in self.structure or self.hangs(item):
                continue
            bottom = box["min"][2]
            if bottom <= self.floor_z + 0.05:
                continue
            below = [o for o, b in self.item_box.items() if o != item and b["max"][2] <= bottom + 0.05
                     and _overlap(box, b)[0] > 0 and _overlap(box, b)[1] > 0]
            support = max((self.item_box[o]["max"][2] for o in below), default=self.floor_z)
            gap = bottom - support
            inside = [o for o, b in self.item_box.items() if o in self._swallowers and o != item
                      and b["min"][2] < bottom < b["max"][2] - 0.05 and _overlap(box, b)[0] > 0.05
                      and _overlap(box, b)[1] > 0.05]
            if gap > 0.05 and inside:
                continue        # it is buried inside something else - the OVERLAP finding says so
            if gap > 0.05:
                height = _size(box)[2]
                hint = ""
                if abs(bottom - self.floor_z - height) <= 0.08 or abs(bottom - 0.75) <= 0.05:
                    hint = (f" - its bottom is at z={bottom:.2f}, about its own height ({height:.2f} m) / a table "
                            f"height: the location was probably given as the TOP height instead of the floor")
                self.add("high" if gap > 0.2 else "medium", "FLOATING", [item],
                         f"'{item}' floats {gap:.2f} m above what is under it",
                         "nothing holds it up" + hint, f"object.move_by(names=['{item}'], offset=[0, 0, {-gap:.2f}])",
                         {"gap_m": round(gap, 3)})

    def check_wall_items(self):
        if not self.walls:
            return
        for item, box in self.item_box.items():
            if not ON_WALL.search(item) or item in self.structure:
                continue
            gaps = []
            for wall in self.walls:
                w = self.item_box[wall]
                gap = max(max(w["min"][k] - box["max"][k], box["min"][k] - w["max"][k]) for k in (0, 1))
                gaps.append((gap, wall))
            gap, wall = min(gaps)
            if gap > 0.1:
                self.add("medium", "NOT ON WALL", [item], f"'{item}' should hang on a wall but the nearest wall "
                         f"('{wall}') is {gap:.2f} m away", "it stands in the air in the middle of the room",
                         f"move it against '{wall}' (object.move_by)", {"gap_m": round(gap, 3)})

    def _touches_wall(self, box) -> bool:
        for wall in self.walls:
            ov = _overlap(box, self.item_box[wall])
            if ov[2] > 0 and min(ov[0], ov[1]) > -0.05 and max(ov[0], ov[1]) > 0:
                return True
        return False

    # -- room
    def _room_centre(self):
        if self.walls:
            box = _union([self.item_box[w] for w in self.walls])
        else:
            box = _union(list(self.item_box.values())) if self.item_box else {"min": [0, 0, 0], "max": [0, 0, 0]}
        return [(box["min"][k] + box["max"][k]) / 2.0 for k in (0, 1)]

    def check_room(self):
        if len(self.walls) < 2:
            return
        room = _union([self.item_box[w] for w in self.walls])
        outside = []
        for item, box in self.item_box.items():
            if item in self.structure:
                continue
            cx = (box["min"][0] + box["max"][0]) / 2.0
            cy = (box["min"][1] + box["max"][1]) / 2.0
            if not (room["min"][0] - 0.05 <= cx <= room["max"][0] + 0.05 and room["min"][1] - 0.05 <= cy <= room["max"][1] + 0.05):
                outside.append((item, cx, cy))
        things = [i for i in self.item_box if i not in self.structure]
        if not things or len(outside) > 0.34 * len(things):
            return     # most things are outside: these walls are not the room the scene is in (a campus wall ...)
        for item, cx, cy in outside:
            if True:
                self.add("medium", "OUTSIDE ROOM", [item], f"'{item}' stands outside the room's walls",
                         f"its centre ({cx:.2f}, {cy:.2f}) is outside x {room['min'][0]:.2f}..{room['max'][0]:.2f}, "
                         f"y {room['min'][1]:.2f}..{room['max'][1]:.2f}", "move it inside the room (object.move_by)")

    # -- lights
    def check_lights(self):
        lights = [o for o in self.objects.values() if o["type"] == "LIGHT"]
        if not lights:
            self.add("medium", "LIGHTS", [], "there are no lights", "only the world light shines", "light.create")
        spots: Dict[tuple, List[str]] = {}
        for light in lights:
            key = tuple(round(v, 2) for v in light["location"])
            spots.setdefault(key, []).append(light["name"])
            info = light.get("light") or {}
            if info.get("energy", 1) <= 0:
                self.add("medium", "LIGHTS", [light["name"]], f"'{light['name']}' has no energy", "it gives no light",
                         "set its energy")
            if info.get("type") in ("POINT", "SPOT", "AREA"):
                for item, box in self.item_box.items():
                    if all(box["min"][k] + 0.02 < light["location"][k] < box["max"][k] - 0.02 for k in range(3)) \
                            and not self.hangs(item) and item not in self.structure \
                            and not self.items[item].get("building"):
                        self.add("medium", "LIGHTS", [light["name"], item],
                                 f"'{light['name']}' is inside '{item}'", "its light is blocked",
                                 f"move the light out of '{item}'")
                        break
        for key, names in spots.items():
            if len(names) > 1:
                self.add("high", "LIGHTS", names, f"{len(names)} lights are on the very same spot {list(key)}",
                         "usually their positions were not applied (e.g. a wrong argument name)",
                         "give each light its own location")

    # -- materials
    def check_materials(self):
        bare = [n for n, o in self.solid.items() if not any(o.get("materials") or [])]
        if bare:
            self.add("medium", "MATERIAL", bare, f"{len(bare)} object(s) have no material (plain grey / white)",
                     "they look unfinished", "material.recipe(recipe=..., assign_to=[...])")

    # -- scale
    def check_scale(self):
        for n, o in self.objects.items():
            s = o.get("scale") or [1, 1, 1]
            if any(abs(v) < 1e-4 for v in s):
                self.add("high", "SCALE", [n], f"'{n}' has a zero scale {_fmt(s)}", "it is flat / invisible",
                         "object.transform with a real scale")
            elif any(v < 0 for v in s):
                self.add("medium", "SCALE", [n], f"'{n}' has a negative scale {_fmt(s)}", "it is mirrored inside out",
                         "use positive scale and rotate instead")
            elif max(abs(v) for v in s) > 200 and o["type"] == "MESH":
                self.add("low", "SCALE", [n], f"'{n}' has a huge scale {_fmt(s)}", "check its size", "")

    def check_sizes(self):
        for item, box in self.item_box.items():
            kind = _kind(item)
            if not kind or item in self.structure or self.items[item].get("building") or GROUP_WORDS.search(item):
                continue
            tallest = max(_size(box))
            low, high = TYPICAL_SIZE[kind]
            if tallest < low * 0.5 or tallest > high * 1.8:
                self.add("medium", "SIZE", [item], f"'{item}' is {tallest:.2f} m at its longest side",
                         f"a real {kind} is about {low}-{high} m", "resize it (object.transform scale)",
                         {"size_m": [round(v, 2) for v in _size(box)]})
            if max(_size(box)) < 0.005:
                self.add("medium", "SIZE", [item], f"'{item}' is almost nothing ({max(_size(box)) * 1000:.1f} mm)",
                         "it cannot be seen", "give it a real size or delete it")

    def check_tilt(self):
        for n, o in self.objects.items():
            if o["type"] != "MESH" or STRUCTURE.search(n) or HANGS.search(n):
                continue
            rx, ry = (o.get("rotation") or [0, 0, 0])[:2]
            off = [abs(((r + math.pi / 4) % (math.pi / 2)) - math.pi / 4) for r in (rx, ry)]
            if max(off) > math.radians(4) and (TABLE.search(n) or TUCK.search(n) or re.search(r"shelf|bed|sofa|cabinet|wardrobe", n, re.I)):
                self.add("medium", "TILTED", [n], f"'{n}' leans {math.degrees(max(off)):.0f} degrees",
                         "furniture should stand upright", f"object.transform(name='{n}', rotation=[0, 0, current z])")

    def check_duplicates(self):
        seen: Dict[tuple, str] = {}
        for n, o in self.solid.items():
            key = (o["type"], tuple(round(v, 2) for v in o["box"]["min"]), tuple(round(v, 2) for v in o["box"]["max"]))
            if key in seen:
                self.add("medium", "DUPLICATE", [seen[key], n], f"'{n}' is an exact copy of '{seen[key]}' in the same place",
                         "two objects on top of each other (flicker in renders)", f"object.delete(name='{n}')")
            else:
                seen[key] = n

    def check_defaults(self):
        for n, o in self.solid.items():
            if DEFAULT_NAMES.match(n):
                size = _size(o["box"])
                self.add("medium", "DEFAULT", [n], f"'{n}' is a default Blender primitive ({_fmt(size)} m)",
                         "usually left over from the start file or a forgotten step",
                         f"delete it (object.delete(name='{n}')) or give it a real name, size and material")

    def check_collections(self):
        empty = [c for c, count in (self.snapshot.get("collections") or {}).items()
                 if count == 0 and c not in ("Collection", "Scene Collection")]
        if empty:
            self.add("low", "COLLECTIONS", empty, f"empty collection(s): {', '.join(empty)}",
                     "nothing was sorted into them", "scene.organize or delete them")
        asked = re.findall(r"collections?\s*:\s*([A-Z][\w ,]*?)(?:\.|\n|$)", self.request)
        wanted = [w.strip() for part in asked for w in re.split(r",|\band\b", part) if w.strip()]
        if wanted:
            missing = [w for w in wanted if w not in (self.snapshot.get("collections") or {})]
            if missing:
                self.add("medium", "COLLECTIONS", missing, f"asked collections missing: {', '.join(missing)}",
                         "the request named them", "scene.organize(collections=[...])")

    def check_request(self):
        if not self.request:
            return
        text = self.request.lower()
        names = (" ".join(self.objects) + " " + " ".join(self._materials(i) for i in self.items)).lower()
        missing = []
        for word in REQUEST_WORDS:
            if not re.search(rf"\b{word}s?\b", text):
                continue
            options = [word] + SYNONYMS.get(word, [])
            if not any(opt in names for opt in options):
                missing.append(word)
        if missing:
            self.add("medium", "MISSING?", missing, "the request names these but no object name mentions them: "
                     + ", ".join(missing), "they may not have been built (or have another name)",
                     "build them, or check the names with scene.inspect")

    def check_names(self):
        generic = [n for n in self.solid if GENERIC.match(n)]
        for n in generic:
            o = self.solid[n]
            size = _size(o["box"])
            guess = "a wall" if n in self.shape_walls else ("a window / glass" if self._glassy(n) else "")
            self.add("medium", "NAME", [n], f"'{n}' has a tool's default name ({_fmt(size)} m"
                     + (f", looks like {guess}" if guess else "") + ")",
                     "nobody (the checks, the vision reviewer, you) can tell what it is meant to be - a request item "
                     "with this name counts as missing", f"object.rename(name='{n}', new_name='<what it is>')")

    def check_wall_shapes(self):
        for k in self.structure:
            if not ROOM_WALL.search(k) or k in self.shape_walls:
                continue
            size = _size(self.item_box[k])
            length, thick = max(size[:2]), min(size[:2])
            if thick >= 3.0:
                continue        # a wall all around a site (a closed ring): its box is not its shape
            if length < 1.5 or thick > 0.6:
                self.add("high", "WALL SHAPE", [k], f"'{k}' is {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f} m - "
                         f"that is a pillar / block, not a wall", "a wall is long and thin (e.g. 4 x 0.2 x 3 m)",
                         f"object.transform(name='{k}', scale=...) to the room's side length")
        for k in self.walls:
            b = self.item_box[k]
            if not (ROOM_WALL.search(k) or k in self.shape_walls):
                continue
            if b["min"][2] > self.floor_z + 0.1:
                self.add("high", "WALL SHAPE", [k], f"wall '{k}' starts {b['min'][2] - self.floor_z:.2f} m above the "
                         f"floor (bottom z={b['min'][2]:.2f})", "walls stand on the floor",
                         f"object.move_by(names=['{k}'], offset=[0, 0, {-(b['min'][2] - self.floor_z):.2f}])")

    def check_flat_things(self):
        for item, box in self.item_box.items():
            if not FLAT_KINDS.search(item) or self.items[item]["model"] or GROUP_WORDS.search(item):
                continue
            size = sorted(_size(box))
            if all(abs(v - 2.0) < 0.01 for v in size):
                pass
            elif size[0] > 0.25:
                self.add("high", "SIZE", [item], f"'{item}' is {size[2]:.2f} x {size[1]:.2f} x {size[0]:.2f} m - "
                         "it should be flat", "a whiteboard / painting / window / door / rug is thin",
                         f"object.transform(name='{item}', scale=...) so one side is a few cm")
            if all(abs(v - 2.0) < 0.01 for v in size):
                self.add("high", "SIZE", [item], f"'{item}' is still the 2 x 2 x 2 m start cube",
                         "it was never given its real size", f"object.transform(name='{item}', scale=...)")

    def check_startup_leftovers(self):
        for n, o in self.objects.items():
            loc = o.get("location") or [0, 0, 0]
            if o["type"] == "LIGHT" and re.match(r"^Light(\.\d+)?$", n) and \
                    all(abs(a - b) < 0.05 for a, b in zip(loc, STARTUP_LIGHT)):
                self.add("medium", "DEFAULT", [n], f"'{n}' is Blender's start-up light ({(o.get('light') or {}).get('energy', '?')} W "
                         "at [4.08, 1.01, 5.90]) - it was never removed or placed",
                         "it lights the scene from a random spot outside / above the room",
                         f"object.delete(name='{n}') or move it where a light is wanted")
            if o["type"] == "CAMERA" and all(abs(a - b) < 0.05 for a, b in zip(loc, STARTUP_CAMERA)) \
                    and re.search(r"camera", self.request, re.I):
                self.add("medium", "CAMERA", [n], f"'{n}' is still at Blender's start position [7.36, -6.93, 4.96]",
                         "the request asked for a camera view, but the camera was never placed",
                         "camera.create / camera.set at the asked spot")

    def check_console(self):
        errors = [line.strip() for line in self.console.splitlines()
                  if re.search(r"Traceback|Error|Exception|failed", line) and "warning" not in line.lower()]
        if errors:
            self.add("high", "CONSOLE", [], f"{len(errors)} error line(s) in the Blender console",
                     " | ".join(errors[:5])[:600], "read the console lines above")


def _push(big: dict, small: dict) -> List[float]:
    best = None
    for k in (0, 1):
        for amount, sign in ((big["max"][k] - small["min"][k], 1.0), (small["max"][k] - big["min"][k], -1.0)):
            if best is None or amount < best[0]:
                best = (amount, k, sign)
    move = [0.0, 0.0, 0.0]
    move[best[1]] = round(best[2] * (best[0] + 0.05), 2)
    return move


# ---------------------------------------------------------------- report
def find_errors(snapshot: dict, request: str = "", console: str = "") -> List[dict]:
    return Finder(snapshot, request, console).run()


def format_errors(findings: List[dict], snapshot: dict, request: str = "") -> str:
    objects = snapshot.get("objects", [])
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in ("high", "medium", "low")}
    lines = ["BLENDER AI AGENT - ERROR FINDER (reads the scene, changes nothing)",
             f"time      {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"objects   {len(objects)}   camera: {snapshot.get('camera') or 'NONE'}   engine: {snapshot.get('engine', '?')}",
             f"found     {len(findings)} problem(s): {counts['high']} high, {counts['medium']} medium, {counts['low']} low",
             "=" * 100]
    if request:
        lines += ["REQUEST:", request.strip()[:2500], "=" * 100]
    if not findings:
        lines.append("No problem found.")
    by_kind: Dict[str, List[dict]] = {}
    for f in findings:
        by_kind.setdefault(f["kind"], []).append(f)
    number = 0
    for kind, group in by_kind.items():
        lines += ["", f"{kind} ({len(group)})", "-" * 100]
        for f in group:
            number += 1
            lines.append(f"{number:3d}. [{f['severity'].upper()}] {f['what']}")
            if f.get("why"):
                lines.append(f"      why:  {f['why']}")
            if f.get("fix"):
                lines.append(f"      fix:  {f['fix']}")
            if f.get("objects"):
                lines.append(f"      objects: {', '.join(map(str, f['objects']))[:400]}")
            for key, value in (f.get("numbers") or {}).items():
                lines.append(f"      {key}: {value}")
    lines += ["", "=" * 100, "EVERY OBJECT (name | type | world box min -> max | size | materials | in camera view)", "-" * 100]
    for o in sorted(objects, key=lambda o: o["name"]):
        box = o.get("box")
        where = f"{_fmt(box['min'])} -> {_fmt(box['max'])} size {_fmt(_size(box))}" if box else f"at {_fmt(o['location'])}"
        view = "" if o.get("in_view") is None else f" | view {o['in_view'] * 100:.0f}%"
        mats = ",".join(m for m in (o.get("materials") or []) if m) or "-"
        extra = ""
        if o.get("light"):
            extra = f" | {o['light']['type']} {o['light']['energy']} W"
        lines.append(f"{o['name']} | {o['type']} | {where} | mat {mats}{view}{extra}"
                     + (" | HIDDEN" if o.get("hidden") else ""))
    return "\n".join(lines) + "\n"


def errors_folder() -> str:
    folder = os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "errors")
    os.makedirs(folder, exist_ok=True)
    return folder


def write_errors(bridge, request: str = "", console: str = "", folder: str = "") -> Optional[str]:
    """Snapshot the scene, find every problem, write errors.txt (+ errors.json). Returns the .txt path."""
    snapshot = bridge.scene_snapshot()
    findings = find_errors(snapshot, request, console)
    target = folder or errors_folder()
    os.makedirs(target, exist_ok=True)
    stem = "errors" if folder else time.strftime("%Y%m%d_%H%M%S") + "_errors"
    path = os.path.join(target, stem + ".txt")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(format_errors(findings, snapshot, request))
    with open(os.path.join(target, stem + ".json"), "w", encoding="utf-8") as handle:
        json.dump({"findings": findings, "snapshot": snapshot}, handle, indent=1, default=str)
    return path
