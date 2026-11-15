"""Geometry checks after a request: things a render review often misses or the model ignores.

  floating      the object's lowest point is above the ground and nothing is under it
  sunk          the whole object is below the ground
  no material   a visible object still has no material (renders as plain white / grey)
  on a path     a bench / lamp / tree stands in the middle of a path or road (curve.create profile="flat")
  path in water a path runs straight through a pond, pool or fountain
  uneven        repeated parts (posts, legs, columns, lamps, seats ...) that should match have different heights
  door          a door / gate whose bottom is not on the floor (floating in front of a wall, or sunk)
  default size  an object.create primitive left at its default 2 m size (a goal post as a 2 m-wide cylinder)
  oversized     a known thing (bench, lamp, tree ...) is many times its real size - usually an
                imported model whose 0.01 import scale was "fixed" to 1.0

Every finding names the object and the exact tool call that fixes it, so the automatic fix round can act on it.
Works on real Blender (bridge.measure_objects) and on the test fakes.
"""

import re
from typing import Dict, Iterable, List, Optional

WATER = re.compile(r"pond|pool|lake|fountain|water|basin|river", re.IGNORECASE)
GROUND_TOLERANCE = 0.05
# Natural things vary on purpose; repeats of these are not expected to match.
NATURAL = re.compile(r"tree|bush|rock|stone|boulder|flower|plant|grass|cloud|crown|blob|frond|leaf|leaves|branch|"
                     r"mushroom|coconut|hill|mountain|terrain|wave|flame|fire|smoke|person|people|human|character|"
                     r"book|novel|magazine|file|folder|pillow|cushion|cup|vase|bottle|jar|toy|fruit|candle|crystal",
                     re.IGNORECASE)
DOOR = re.compile(r"door|gate|entrance", re.IGNORECASE)
DOOR_PARTS = re.compile(r"handle|knob|frame_top|lintel|header|arch|sign|window|glass|panel_top|transom", re.IGNORECASE)
THIN_PART = re.compile(r"post|bar\b|crossbar|pole|leg|rail|rod|beam|stick|stump|wire|mast|pillar|column|handle|"
                       r"line|plank|board|frame|edge|rim|net", re.IGNORECASE)
OVERSIZE_FACTOR = 5.0
OVERSIZE_MIN_M = 5.0
SUPPORT_TOLERANCE = 0.08
CHECKED_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT"}

# Things that are meant to hang in the air.
AIRBORNE = re.compile(
    r"cloud|sky|bird|star|moon|sun|planet|asteroid|comet|balloon|drone|aircraft|airplane|plane_fly|helicopter|"
    r"flame|fire|smoke|spark|ember|steam|mist|fog|particle|glow|halo|light|lamp_shade|chandelier|pendant|ceiling|"
    r"roof|canopy|leaf|leaves|foliage|crown|fruit|sign|banner|flag|wire|cable|rope|beam|shelf|picture|painting|frame|"
    r"window|curtain|clock|hanging|float|fly|flying|bubble|snowflake|rain|spray|foam|splash|water_fall|waterfall_water",
    re.IGNORECASE)


def _boxes(bridge, names: Iterable[str]) -> Dict[str, dict]:
    boxes = {}
    for name in names:
        try:
            box = bridge.measure_objects([name])
        except Exception:  # noqa: BLE001
            box = None
        if box:
            boxes[name] = box
    return boxes


def _xy_overlap(a: dict, b: dict) -> bool:
    return (min(a["max"][0], b["max"][0]) - max(a["min"][0], b["min"][0]) > 0 and
            min(a["max"][1], b["max"][1]) - max(a["min"][1], b["min"][1]) > 0)


def _has_material(obj) -> Optional[bool]:
    slots = getattr(obj, "material_slots", None)
    if slots is not None:
        try:
            return any(slot.material is not None for slot in slots)
        except Exception:  # noqa: BLE001
            return None
    if hasattr(obj, "material_name"):
        return bool(obj.material_name)
    return None


def _parent_name(obj) -> Optional[str]:
    parent = getattr(obj, "parent", None)
    return getattr(parent, "name", None) if parent is not None else None


def _supported(name: str, boxes: Dict[str, dict], group) -> bool:
    """Something outside this group is under the object."""
    box, bottom = boxes[name], boxes[name]["min"][2]
    return any(other not in group and _xy_overlap(box, obox)
               and obox["min"][2] - SUPPORT_TOLERANCE <= bottom <= obox["max"][2] + SUPPORT_TOLERANCE
               for other, obox in boxes.items())


def repeat_key(name: str) -> str:
    """'park_lamp2_pole.001' -> 'park_lamp#_pole', 'leg_3' -> 'leg_#': names that differ only by a number."""
    base = re.sub(r"\.\d{3}$", "", name)
    return re.sub(r"\d+", "#", base).lower()


def _uneven_repeats(names: List[str], boxes: Dict[str, dict]) -> List[Dict[str, str]]:
    groups: Dict[str, List[str]] = {}
    for name in names:
        if name in boxes and not NATURAL.search(name):
            groups.setdefault(repeat_key(name), []).append(name)
    problems = []
    for key, members in groups.items():
        if len(members) < 2:
            continue
        heights = {n: boxes[n]["max"][2] - boxes[n]["min"][2] for n in members}
        tallest, shortest = max(heights.values()), min(heights.values())
        if tallest < 0.05 or (tallest - shortest) < max(0.03, 0.04 * tallest):
            continue
        typical = sorted(heights.values())[len(heights) // 2]
        odd = [n for n, h in heights.items() if abs(h - typical) >= max(0.03, 0.04 * typical)]
        if not odd:
            continue
        severity = "high" if (tallest - shortest) > 0.1 * tallest else "medium"
        listed = ", ".join(f"{n} {heights[n]:.2f} m" for n in odd[:6])
        problems.append({"severity": severity, "where": f"{key.replace('#', '*')} ({len(members)} parts)",
                         "issue": f"repeated parts are not the same height - most are {typical:.2f} m but {listed}",
                         "fix": f"object.transform each odd one (scale z = current x {typical:.2f} / its height) so all are "
                                f"{typical:.2f} m, then object.snap_to_ground or object.place_on to re-seat them"})
        if len(problems) >= 6:
            break
    return problems


def _door_problems(names: List[str], boxes: Dict[str, dict]) -> List[Dict[str, str]]:
    problems = []
    for name in names:
        if name not in boxes or not DOOR.search(name) or DOOR_PARTS.search(name):
            continue
        box = boxes[name]
        bottom, height = box["min"][2], box["max"][2] - box["min"][2]
        if height < 0.8:
            continue                                         # a doormat, a knob, a step: not the door leaf
        floors = [0.0] + [o["max"][2] for other, o in boxes.items() if other != name and _xy_overlap(box, o)
                          and o["max"][2] <= bottom + 0.3 and (o["max"][0] - o["min"][0]) * (o["max"][1] - o["min"][1]) > 0.5]
        floor = min(floors, key=lambda z: abs(z - bottom))
        gap = bottom - floor
        if abs(gap) > 0.03:
            where = "above" if gap > 0 else "below"
            problems.append({"severity": "high", "where": name,
                             "issue": f"its bottom is {abs(gap):.2f} m {where} the floor (z={floor:.2f}) - a door must stand on the floor",
                             "fix": f"object.transform(name='{name}', location=[x, y, z {'-' if gap > 0 else '+'} {abs(gap):.2f}]) "
                                    "so the bottom is exactly on the floor; keep it flush in the wall opening"})
        if height > 3.2 and "gate" not in name.lower() and "entrance" not in name.lower():
            problems.append({"severity": "medium", "where": name,
                             "issue": f"is {height:.2f} m tall - a normal door is about 2.1 m",
                             "fix": f"object.transform(name='{name}', scale z so the height is about 2.1 m) then re-seat it on the floor"})
    return problems[:6]


def _default_primitive(obj, box: dict) -> bool:
    scale = [float(v) for v in (getattr(obj, "scale", None) or [1.0, 1.0, 1.0])]
    if any(abs(v - 1.0) > 1e-4 for v in scale) or getattr(obj, "type", "MESH") != "MESH":
        return False
    size = [box["max"][k] - box["min"][k] for k in range(3)]
    return all(abs(v - 2.0) < 0.02 for v in size)


def _oversized(name: str, obj, box: dict) -> Optional[Dict[str, str]]:
    from ..tools.local_assets_tools import typical_height

    expected = typical_height(name)
    if not expected:
        return None
    height = box["max"][2] - box["min"][2]
    if height <= max(OVERSIZE_MIN_M, expected * OVERSIZE_FACTOR):
        return None
    factor = expected / height
    scale = [round(float(v) * factor, 4) for v in (getattr(obj, "scale", None) or [1.0, 1.0, 1.0])]
    return {"severity": "high", "where": name,
            "issue": f"is {height:.1f} m tall but a real one is about {expected:g} m - it was scaled up by mistake "
                     f"and hides the rest of the scene",
            "fix": f"object.transform(name='{name}', scale={scale}) then object.snap_to_ground(names=['{name}'])"}


def _path_problems(bridge, targets: List[str], boxes: Dict[str, dict]) -> List[Dict[str, str]]:
    from ..tools import paths as _paths
    from ..tools.placement_tools import path_blockers

    try:
        live = _paths.live_paths(bridge)
    except Exception:  # noqa: BLE001
        return []
    if not live:
        return []
    problems: List[Dict[str, str]] = []
    try:
        blockers = path_blockers(bridge, targets, live)
    except Exception:  # noqa: BLE001
        blockers = []
    for item in blockers[:8]:
        parts = item["names"]
        label = parts[0] if len(parts) == 1 else f"{parts[0]} (+{len(parts) - 1} parts)"
        listed = ", ".join(f"'{n}'" for n in parts[:20])
        problems.append({"severity": "high", "where": label,
                         "issue": f"stands in the middle of the path '{item['path']}' and blocks it",
                         "fix": f"object.move_off_path(names=[{listed}]) - moves it to the path edge"})
    # paths that run straight through water
    for water, box in boxes.items():
        if not WATER.search(water) or water in live:
            continue
        cx, cy = (box["min"][0] + box["max"][0]) / 2.0, (box["min"][1] + box["max"][1]) / 2.0
        rx, ry = 0.42 * (box["max"][0] - box["min"][0]), 0.42 * (box["max"][1] - box["min"][1])
        if rx < 0.3 or ry < 0.3:
            continue
        for path_name, entry in live.items():
            crosses = False
            for stroke in entry["strokes"]:
                for (ax, ay), (bx, by) in zip(stroke, stroke[1:]):
                    steps = max(1, int(((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5 / 0.4))
                    for i in range(steps + 1):
                        x, y = ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps
                        if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 < 1.0:
                            crosses = True
                            break
                    if crosses:
                        break
                if crosses:
                    break
            if crosses:
                radius = max(box["max"][0] - box["min"][0], box["max"][1] - box["min"][1]) / 2.0
                problems.append({
                    "severity": "high", "where": path_name,
                    "issue": f"runs straight through '{water}' (the path shows through the water)",
                    "fix": (f"object.delete(name='{path_name}') then curve.create(name='{path_name}', profile='flat', "
                            f"width={entry['width']:g}, strokes=[...]) with lines that stop at the edge of '{water}' "
                            f"(centre [{cx:.1f}, {cy:.1f}], radius {radius:.1f} m + 0.5 m) or go around it")})
    return problems


# Multi-part objects made by one generator call (mesh.building, mesh.boundary_wall, mesh.grandstand ...): all the
# doors of a 6-storey block are ONE object, so "an 18 m tall door" is right there - never shrink or move them.
_ASSEMBLY_MARKERS = (("_structure", "_walls"), ("_wall", "_pillars"), ("", "_seats"))


# ---------------------------------------------------------------- things standing inside each other
_STANDING = ("furniture", "decor", "sport", "vehicle", "camp", "structure", "light", "nature")
_TUCK = re.compile(r"chair|stool|seat|bench")             # chairs may stand under a table
_TABLE = re.compile(r"table|desk")
_WALL = re.compile(r"wall|partition", re.IGNORECASE)
CLASH_MIN_M = 0.08                                        # touching is fine, 8 cm inside is a mistake


def library_items(names: Iterable[str]) -> Dict[str, List[str]]:
    """Group library parts into the model they belong to: 'bookshelf_shelf', 'bookshelf_books' -> 'bookshelf';
    a second copy ('bookshelf_shelf.001') -> 'bookshelf.001'."""
    try:
        from ..tools.library_tools import load_library
        library = load_library()
    except Exception:  # noqa: BLE001
        return {}
    models = sorted(library, key=len, reverse=True)
    items: Dict[str, List[str]] = {}
    for name in names:
        base, dot, copy = name.partition(".")
        for model in models:
            if base.startswith(model + "_"):
                items.setdefault(model + (dot + copy if copy.isdigit() else ""), []).append(name)
                break
    return items


def _item_box(parts: List[str], boxes: Dict[str, dict]) -> Optional[dict]:
    got = [boxes[p] for p in parts if p in boxes]
    if not got:
        return None
    return {"min": [min(b["min"][k] for b in got) for k in range(3)],
            "max": [max(b["max"][k] for b in got) for k in range(3)]}


def _overlap(a: dict, b: dict) -> List[float]:
    return [min(a["max"][k], b["max"][k]) - max(a["min"][k], b["min"][k]) for k in range(3)]


def _push(a: dict, b: dict) -> List[float]:
    """The smallest sideways move that takes box b out of box a (x or y)."""
    best = None
    for k in (0, 1):
        right = a["max"][k] - b["min"][k]          # move b towards +k
        left = b["max"][k] - a["min"][k]           # move b towards -k
        for amount, sign in ((right, 1.0), (left, -1.0)):
            if best is None or amount < best[0]:
                best = (amount, k, sign)
    move = [0.0, 0.0, 0.0]
    move[best[1]] = round(best[2] * (best[0] + 0.05), 2)
    return move


def _clash_problems(targets: List[str], boxes: Dict[str, dict]) -> List[Dict[str, str]]:
    """Furniture standing inside other furniture or inside a wall (a bookshelf through a wardrobe)."""
    try:
        from ..tools.library_tools import load_library
        library = load_library()
    except Exception:  # noqa: BLE001
        return []
    items = library_items(targets)
    solid = {}
    for item, parts in items.items():
        spec = library.get(item.split(".")[0], {})
        if spec.get("category") not in _STANDING or spec.get("hangs"):
            continue
        box = _item_box(parts, boxes)
        if box is None or box["max"][2] - box["min"][2] < 0.05:      # rugs and mats lie under things on purpose
            continue
        solid[item] = (box, parts)
    problems: List[Dict[str, str]] = []
    names = sorted(solid)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            a, a_parts = solid[first]
            b, b_parts = solid[second]
            dx, dy, dz = _overlap(a, b)
            if min(dx, dy) < CLASH_MIN_M or dz < 0.1:
                continue
            kinds = (first.split(".")[0], second.split(".")[0])
            if (_TUCK.search(kinds[0]) and _TABLE.search(kinds[1])) or (_TUCK.search(kinds[1]) and _TABLE.search(kinds[0])):
                continue
            # move the smaller one out of the bigger one
            vol = lambda box: max(1e-6, (box["max"][0] - box["min"][0]) * (box["max"][1] - box["min"][1]))
            big, small = ((first, a), (second, b)) if vol(a) >= vol(b) else ((second, b), (first, a))
            move = _push(big[1], small[1])
            parts = solid[small[0]][1]
            problems.append({"severity": "high", "where": small[0],
                             "issue": f"stands inside '{big[0]}' ({dx:.2f} x {dy:.2f} m of them overlap) - two pieces of "
                                      "furniture cannot share the same space",
                             "fix": f"object.move_by(names=['{small[0]}'], offset={move}) - moves all its parts "
                                    f"({', '.join(parts[:4])}{' ...' if len(parts) > 4 else ''}) out of '{big[0]}'"})
            if len(problems) >= 6:
                return problems
    walls = [n for n in targets if _WALL.search(n) and n in boxes and n not in sum((p for _b, p in solid.values()), [])]
    # the room is where the furniture is: a piece in a wall is pushed back towards it, never out of the room
    centre = [sum((b["min"][k] + b["max"][k]) / 2.0 for b, _p in solid.values()) / max(1, len(solid)) for k in (0, 1)]
    for item, (box, parts) in sorted(solid.items()):
        for wall in walls:
            w = boxes[wall]
            thin = min(w["max"][0] - w["min"][0], w["max"][1] - w["min"][1])
            if thin > 0.8:                                  # not a plain straight wall
                continue
            dx, dy, dz = _overlap(box, w)
            if min(dx, dy) < CLASH_MIN_M or dz < 0.3:
                continue
            k = 0 if (w["max"][0] - w["min"][0]) <= (w["max"][1] - w["min"][1]) else 1     # the wall's thin axis
            wall_mid = (w["min"][k] + w["max"][k]) / 2.0
            move = [0.0, 0.0, 0.0]
            if centre[k] < wall_mid:
                move[k] = round(w["min"][k] - box["max"][k] - 0.03, 2)
            else:
                move[k] = round(w["max"][k] - box["min"][k] + 0.03, 2)
            problems.append({"severity": "high", "where": item,
                             "issue": f"goes {min(dx, dy):.2f} m into the wall '{wall}'",
                             "fix": f"object.move_by(names=['{item}'], offset={move}) - all its parts, so it stands in "
                                    "front of the wall"})
            break
        if len(problems) >= 8:
            break
    return problems


def assembly_parts(names: Iterable[str]) -> set:
    names = set(names)
    parts = set()
    for name in names:
        for first, second in _ASSEMBLY_MARKERS:
            if not first or not name.endswith(first):
                continue
            prefix = name[: -len(first)]
            if prefix and prefix + second in names:
                parts.update(n for n in names if n.startswith(prefix + "_"))
    for name in names:                                          # grandstand: 'stand' + 'stand_seats' (+ _roof)
        if name + "_seats" in names:
            parts.update({name, name + "_seats", name + "_roof"} & names)
    return parts


def geometry_problems(bridge, names: Iterable[str], max_scene_objects: int = 300) -> List[Dict[str, str]]:
    """Problems for the given (new or changed) objects, in the same shape as the vision review's problems."""
    try:
        scene = [o for o in bridge.get_objects() if getattr(o, "type", "") in CHECKED_TYPES][:max_scene_objects]
    except Exception:  # noqa: BLE001
        return []
    by_name = {o.name: o for o in scene}
    targets = [n for n in dict.fromkeys(names) if n in by_name and not _parent_name(by_name[n])]
    if not targets:
        return []
    boxes = _boxes(bridge, by_name)
    problems: List[Dict[str, str]] = []
    floating, unpainted, bare_ground = [], [], []
    assembled = assembly_parts(by_name)
    for name in targets:
        box = boxes.get(name)
        if box is None:
            continue
        bottom, top = box["min"][2], box["max"][2]
        if name in assembled:                       # sized and placed by its generator: only "below ground" applies
            if top < -GROUND_TOLERANCE:
                problems.append({"severity": "high", "where": name, "issue": f"is completely below the ground (top at z={top:.2f})",
                                 "fix": f"object.snap_to_ground(names=['{name}'])"})
            continue
        too_big = _oversized(name, by_name[name], box)
        if too_big:
            problems.append(too_big)
            continue
        if _default_primitive(by_name[name], box):
            thin = bool(THIN_PART.search(name))
            problems.append({"severity": "high" if thin else "medium", "where": name,
                             "issue": "is still the default 2 x 2 x 2 m primitive - it was never given its real size",
                             "fix": f"object.transform(name='{name}', scale=[...]) to its real size "
                                    "(cylinder: [radius, radius, half height]; cube: half of each side), then "
                                    f"object.snap_to_ground(names=['{name}']) if it stands on the ground"})
        if top < -GROUND_TOLERANCE:
            problems.append({"severity": "high", "where": name, "issue": f"is completely below the ground (top at z={top:.2f})",
                             "fix": f"object.snap_to_ground(names=['{name}'])"})
            continue
        if bottom > GROUND_TOLERANCE and not AIRBORNE.search(name):
            supported = any(
                other != name and _xy_overlap(box, obox)
                and obox["min"][2] - SUPPORT_TOLERANCE <= bottom <= obox["max"][2] + SUPPORT_TOLERANCE
                for other, obox in boxes.items())
            if not supported:
                floating.append((name, bottom))
        if _has_material(by_name[name]) is False:
            footprint = (box["max"][0] - box["min"][0]) * (box["max"][1] - box["min"][1])
            if footprint >= 4.0 and top - bottom < 0.5:
                bare_ground.append(name)                     # big flat surface left white: very visible
            else:
                unpainted.append(name)

    if floating:
        from ..tools.placement_tools import connected_groups
        floating_names = {n for n, _ in floating}
        # a part counts as floating only if its whole connected model floats
        groups = connected_groups(boxes)
        reported = set()
        for group in groups:
            if not floating_names & set(group):
                continue
            bottom = min(boxes[n]["min"][2] for n in group)
            if bottom <= GROUND_TOLERANCE or any(AIRBORNE.search(n) is None and _supported(n, boxes, group) for n in group
                                                   if boxes[n]["min"][2] - bottom <= SUPPORT_TOLERANCE):
                continue
            members = [n for n in group if n in floating_names or n in targets]
            listed = ", ".join(f"'{n}'" for n in members[:12])
            label = members[0] if len(members) == 1 else f"{members[0]} (+{len(members) - 1} parts)"
            problems.append({"severity": "high", "where": label,
                             "issue": f"floats {bottom:.2f} m above the ground with nothing under it",
                             "fix": f"object.snap_to_ground(names=[{listed}]) — the parts move together"})
            reported.add(id(group))
            if len(reported) >= 8:
                break
    for name in bare_ground[:4]:
        low = name.lower()
        recipe = "asphalt" if re.search(r"road|street|parking|drive", low) else \
            "concrete" if re.search(r"path|walk|plaza|pavement|sidewalk|court|floor|deck|slab", low) else "grass"
        problems.append({"severity": "high", "where": name, "issue": "is a large ground/floor surface with no material (plain white)",
                         "fix": f"material.recipe(name='{name}_{recipe}', recipe='{recipe}', assign_to=['{name}']) (or gravel / sand / dirt_ground to suit the place)"})
    problems.extend(_path_problems(bridge, targets, boxes))
    single = [n for n in targets if n not in assembled]
    try:
        problems.extend(_uneven_repeats(single, boxes))
        problems.extend(_door_problems(single, boxes))
        problems.extend(_clash_problems(single, boxes))
    except Exception:  # noqa: BLE001 — a check must never break the result
        pass
    if unpainted:
        shown = ", ".join(unpainted[:8]) + (f" (+{len(unpainted) - 8} more)" if len(unpainted) > 8 else "")
        problems.append({"severity": "medium", "where": shown, "issue": "has no material and renders plain white/grey",
                         "fix": "material.recipe (grass, gravel, concrete, wood_grain, rough_stone, metal_brushed, water, ...) or material.create + material.assign(object_name=..., material_name=...)"})
    return problems
