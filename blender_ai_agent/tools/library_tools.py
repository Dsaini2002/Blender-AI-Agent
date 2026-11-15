"""Model Library Tools"""

import json
import math
import os
from typing import Any, Dict, List, Optional

from .base import Permission, Tool, ToolResult
from .models import ListLibraryInput, PlaceModelInput

_LIBRARY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library", "models.json")
_cache: Dict[str, Any] = {}


def load_library(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    key = path or _LIBRARY_PATH
    if key not in _cache:
        with open(key, "r", encoding="utf-8") as handle:
            _cache[key] = json.load(handle)["models"]
    return _cache[key]


def find_model_by_alias(text: str) -> Optional[str]:
    wanted = (text or "").strip().lower()
    spaced = wanted.replace("_", " ").replace("-", " ")
    for name, spec in load_library().items():
        aliases = spec.get("aliases", [])
        if wanted == name or wanted.replace(" ", "_") == name or wanted in aliases or spaced in aliases:
            return name
    return None


# Close stand-ins for things the library does not have, so a scene still gets a sensible model.
_SUBSTITUTES = (
    (("oak", "maple", "birch", "willow", "elm", "tree", "trees", "sapling"), "round_tree"),
    (("conifer", "spruce", "cedar", "evergreen"), "pine_tree"),
    (("hedge", "shrub", "plant", "flowerbed", "flower"), "bush"),
    (("boulder", "stone", "pebble"), "rock"),
    (("lamp", "light", "streetlight", "lightpole", "pole"), "street_lamp"),
    (("seat",), "park_bench"),
    (("decor", "art", "picture", "frame", "poster"), "wall_art"),
)


def substitute_model(text: str) -> Optional[str]:
    """Best library model for a name it does not have ('palm_tree_large' -> palm_tree, 'oak' -> round_tree)."""
    library = load_library()
    words = [w for w in (text or "").lower().replace("-", "_").replace(" ", "_").split("_") if w]
    best, best_len = None, 0
    for name, spec in library.items():                      # longest alias fully contained in the request
        for alias in [name.replace("_", " ")] + list(spec.get("aliases", [])):
            alias_words = alias.split()
            if alias_words and all(w in words for w in alias_words) and len(alias) > best_len:
                best, best_len = name, len(alias)
    if best:
        return best
    if any(w in ("lamp", "light", "lights", "lamps", "lighting", "bulb", "fixture") for w in words):
        # never a 4 m street lamp for an indoor light (a 'ceiling_lamp' once came out as a street lamp)
        indoor = [("pendant_light", ("ceiling", "pendant", "hanging", "roof", "overhead", "chandelier")),
                  ("table_lamp", ("table", "bedside", "desk", "night", "reading", "side")),
                  ("floor_lamp", ("floor", "standing", "corner", "living", "room", "bedroom", "interior", "indoor"))]
        for model, keys in indoor:
            if model in library and any(w in keys for w in words):
                return model
    for keys, model in _SUBSTITUTES:
        if model in library and any(w in keys for w in words):
            return model
    return None


def _rotate_z(x: float, y: float, yaw: float):
    return (x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw))


def _recipe_params(recipe: str, params: Dict[str, Any], override) -> Dict[str, Any]:
    merged = dict(params or {})
    if override is not None:
        rgb = [float(c) for c in list(override)[:3]]
        if recipe == "wood_grain":
            merged["light"] = rgb + [1.0]
            merged["dark"] = [c * 0.4 for c in rgb] + [1.0]
        else:
            merged["color"] = rgb + [1.0]
    return merged


def _build_recipe_material(bridge, name: str, mat_spec: Dict[str, Any], override):
    recipe = mat_spec.get("recipe")
    if not recipe or not hasattr(bridge, "build_node_material"):
        return None
    try:
        from .shader_nodes import build_recipe
        spec = build_recipe(recipe, _recipe_params(recipe, mat_spec.get("params") or {}, override))
        return bridge.build_node_material(name, spec, True)["name"]
    except (ValueError, KeyError):
        return None


def place_model(bridge, model: str, spec: Dict[str, Any], location, scale: float = 1.0,
                yaw_degrees: float = 0.0, prefix: str = "", colors: Optional[Dict[str, List[float]]] = None):
    prefix = prefix or f"{model}_"
    yaw = math.radians(yaw_degrees)
    colors = colors or {}
    lx, ly, lz = location

    material_names: Dict[str, str] = {}
    for key, mat_spec in spec.get("materials", {}).items():
        color = list(colors.get(key, mat_spec["color"]))
        color = (color + [1.0])[:4] if len(color) == 3 else color
        built = _build_recipe_material(bridge, f"{prefix}{key}_mat", mat_spec, colors.get(key))
        if built is not None:
            material_names[key] = built
            continue
        material = bridge.create_material(name=f"{prefix}{key}_mat", color=color)
        emission = mat_spec.get("emission")
        if emission:
            bridge.modify_material(material.name, emission_color=list(emission["color"]),
                                   emission_strength=emission["strength"])
        material_names[key] = material.name

    created: Dict[str, List[str]] = {"meshes": [], "curves": [], "lights": []}

    for part in spec.get("parts", []):
        ox, oy, oz = part.get("offset", [0.0, 0.0, 0.0])
        rx, ry = _rotate_z(ox * scale, oy * scale, yaw)
        position = [lx + rx, ly + ry, lz + oz * scale]
        part_rotation = list(part.get("rotation", [0.0, 0.0, 0.0]))
        rotation = [part_rotation[0], part_rotation[1], part_rotation[2] + yaw]
        part_name = f"{prefix}{part['name']}"

        if part["kind"] == "mesh_data":
            part_scale = part.get("scale", [1.0, 1.0, 1.0])
            obj = bridge.create_mesh(
                name=part_name, vertices=part["vertices"], faces=part["faces"],
                location=position, rotation=rotation,
                scale=[part_scale[0] * scale, part_scale[1] * scale, part_scale[2] * scale],
                shade_smooth=bool(part.get("smooth", False)),
            )
            created["meshes"].append(obj.name)
        elif part["kind"] == "curve":
            obj = bridge.create_curve(
                name=part_name, points=part["points"], curve_type=part.get("curve_type", "BEZIER"),
                thickness=part.get("thickness", 0.05), closed=part.get("closed", False),
                location=position, rotation=rotation, scale=[scale, scale, scale],
            )
            created["curves"].append(obj.name)
        else:
            obj = bridge.create_object(name=part_name, object_type="MESH",
                                       primitive=part.get("primitive", "CUBE"), location=position)
            part_scale = part.get("scale", [1.0, 1.0, 1.0])
            bridge.transform_object(obj.name, rotation=rotation,
                                    scale=[part_scale[0] * scale, part_scale[1] * scale, part_scale[2] * scale])
            created["meshes"].append(obj.name)

        material_key = part.get("material")
        if material_key in material_names:
            bridge.assign_material(obj.name, material_names[material_key])

    for light_spec in spec.get("lights", []):
        ox, oy, oz = light_spec.get("offset", [0.0, 0.0, 0.0])
        rx, ry = _rotate_z(ox * scale, oy * scale, yaw)
        light_rotation = list(light_spec.get("rotation", [0.0, 0.0, 0.0]))
        light_rotation[2] += yaw
        light_obj = bridge.create_light(
            name=f"{prefix}{light_spec['name']}", light_type=light_spec.get("type", "POINT"),
            location=[lx + rx, ly + ry, lz + oz * scale], rotation=light_rotation,
            color=light_spec.get("color", [1.0, 1.0, 1.0]),
            energy=light_spec.get("energy", 500.0) * scale * scale,
            size=light_spec.get("size", 0.25) * scale,
            **({"spot_angle": light_spec["spot_angle"]} if light_spec.get("spot_angle") else {}),
        )
        created["lights"].append(light_obj.name)

    return created


class LibraryListTool(Tool):
    name = "library.list"
    description = (
        "Lists the ready-made models in the model library (campfire, torch, lantern, pine_tree, "
        "round_tree, bush, rock, log_seat, stool, tent, mushroom, fence, street_lamp, cloud ...) with a "
        "description, category and approximate size in metres [width, depth, height]. Optional "
        "`category` filter: fire, light, nature, camp, structure, sky. Call this when you are not sure "
        "which model names exist, then use library.place."
    )
    permission = Permission.READ_ONLY
    input_model = ListLibraryInput

    def __init__(self, bridge=None):
        self._bridge = bridge

    def run(self, validated_input: ListLibraryInput) -> ToolResult:
        models = []
        for name, spec in load_library().items():
            if validated_input.category and spec.get("category", "").lower() != validated_input.category:
                continue
            models.append({
                "model": name, "category": spec.get("category"), "size_m": spec.get("size"),
                "description": spec.get("description"), "color_keys": list(spec.get("materials", {})),
                "has_light": bool(spec.get("lights")),
            })
        if not models:
            return ToolResult.fail(f"No models in category '{validated_input.category}'.")
        return ToolResult.ok({"models": models, "count": len(models)})


def yaw_to_face(front, direction) -> float:
    """Yaw (degrees) that turns a model whose front is `front` (x, y) to look along `direction` (x, y)."""
    return math.degrees(math.atan2(direction[1], direction[0]) - math.atan2(front[1], front[0]))


class LibraryPlaceTool(Tool):
    name = "library.place"
    description = (
        "Places a complete ready-made model from the model library in ONE call - far more reliable and "
        "better looking than building it from primitives. Examples: model='campfire' (stone ring, logs, "
        "glowing embers, curved tapered flame tongues, warm light), 'torch', 'lantern', 'pine_tree', "
        "'round_tree', 'palm_tree', 'bush', 'rock', 'log_seat', 'park_bench', 'stool', 'tent', 'mushroom', 'fence', "
        "'street_lamp', 'stadium_light', 'cricket_wicket', 'football_goal', 'tennis_net', 'badminton_net', "
        "'volleyball_net', 'basketball_hoop', 'badminton_racket', 'shuttlecock', 'cloud'. Origin of every model = centre of its base on the ground, +Z up. Options: location "
        "[x,y,z]; height (wanted height in metres - the easiest way to get a real size, e.g. a 3 m lamp: height=3) "
        "or scale (uniform multiplier, 1 = natural size); face_towards [x, y] (turns the model's front to that point - "
        "stadium lights at the field centre, benches at a view) or yaw_degrees (turn around the vertical "
        "axis); prefix (name prefix, e.g. 'park_lamp1_'; default '<model>_'); colors (override material colours, e.g. "
        '{"leaves": [0.1, 0.5, 0.1]} - keys come from library.list). Use library.list first if unsure of '
        "the names. Place several models at different locations to compose a scene."
    )
    permission = Permission.SAFE_WRITE
    input_model = PlaceModelInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: PlaceModelInput) -> ToolResult:
        library = load_library()
        model = validated_input.model
        note = None
        if model not in library:
            resolved = find_model_by_alias(model)
            if resolved is None:
                resolved = substitute_model(model)
                if resolved is None:
                    return ToolResult.fail(f"No model named '{model}'. Available: {', '.join(sorted(library))}")
                note = (f"The library has no '{validated_input.model}', so '{resolved}' was placed instead. "
                        "Use the same model for the others.")
            model = resolved
        spec = library[model]

        location = list(validated_input.location or [0.0, 0.0, 0.0])
        try:
            from .field_markings import court_with
            court = court_with(model, float(location[0]), float(location[1]), self._bridge)
        except Exception:  # noqa: BLE001
            court = None
        if court and not str(validated_input.prefix or "").startswith(court):
            return ToolResult.ok({"model": model, "skipped": True, "court": court,
                                  "note": f"'{court}' already has its {model} in the right place (mesh.field_markings "
                                          "placed it) - nothing added. Leave it there."})

        scale = validated_input.scale
        native_height = (spec.get("size") or [0, 0, 0])[2]
        if validated_input.height is not None and native_height > 0:
            scale = max(0.05, min(50.0, validated_input.height / native_height))

        unknown = [k for k in (validated_input.colors or {}) if k not in spec.get("materials", {})]
        if unknown:
            return ToolResult.fail(
                f"Unknown colour key(s) {unknown} for '{model}'. Valid keys: {list(spec.get('materials', {}))}"
            )

        location, yaw_degrees, path_note = self._keep_off_paths(model, spec, scale, validated_input)
        if validated_input.face_towards is not None:
            fx = validated_input.face_towards[0] - location[0]
            fy = validated_input.face_towards[1] - location[1]
            if abs(fx) + abs(fy) > 1e-6:
                yaw_degrees = round(yaw_to_face(spec.get("front") or [0, -1], (fx, fy)), 1)

        created = place_model(
            self._bridge, model, spec, location, scale,
            yaw_degrees, validated_input.prefix, validated_input.colors,
        )

        object_count = len(created["meshes"]) + len(created["curves"])
        from .placement_tools import settle_on_support
        dropped = 0.0
        if float(location[2]) > 0.05 and not spec.get("hangs"):     # up in the air (not a hanging fan / lamp)?
            dropped = settle_on_support(self._bridge, created["meshes"] + created["curves"] + created["lights"])
        result = {
            "yaw_degrees": yaw_degrees,
            "dropped_to_ground_m": dropped or None,
            "model": model,
            "location": [round(c, 3) for c in location],
            "scale": round(scale, 4),
            "object_count": object_count,
            "meshes": created["meshes"],
            "curves": created["curves"],
            "lights": created["lights"],
            "size_m": [round(d * scale, 3) for d in spec.get("size", [])],
        }
        if note:
            result["note"] = note
        if path_note:
            result["moved_off_path"] = path_note
        return ToolResult.ok(result)

    def _held_up_at(self, location, live) -> bool:
        """Something other than the ground, a path or a big flat layout piece is right under this point."""
        measure = getattr(self._bridge, "measure_objects", None)
        if measure is None:
            return False
        x, y, z = location
        try:
            objects = list(self._bridge.get_objects())[:400]
        except Exception:  # noqa: BLE001
            return False
        for obj in objects:
            if obj.name in live or getattr(obj, "type", "MESH") not in ("MESH", "CURVE", "SURFACE", "META", "FONT"):
                continue
            try:
                box = measure([obj.name])
            except Exception:  # noqa: BLE001
                continue
            if not box:
                continue
            height = box["max"][2] - box["min"][2]
            footprint = (box["max"][0] - box["min"][0]) * (box["max"][1] - box["min"][1])
            if height < 0.5 and footprint > 4.0:
                continue                                     # ground / plaza
            if box["min"][0] <= x <= box["max"][0] and box["min"][1] <= y <= box["max"][1] \
                    and abs(box["max"][2] - z) <= 0.15:
                return True
        return False

    def _keep_off_paths(self, model: str, spec: Dict[str, Any], scale: float, v: PlaceModelInput):
        """A prop standing on the ground in the middle of a path is moved to the path's edge;
        a bench there is also turned to face the path."""
        from . import paths as _paths
        location = [float(c) for c in v.location]
        yaw = float(v.yaw_degrees)
        if location[2] > 1.0:
            return location, yaw, None
        live = _paths.live_paths(self._bridge)
        if not live:
            return location, yaw, None
        if location[2] > 0.05 and self._held_up_at(location, live):
            return location, yaw, None                       # on a table / deck: not standing on the path
        size = spec.get("size") or [1.0, 1.0, 1.0]
        if "tree" in model:
            radius = min(0.35 * scale, 0.8)                  # the trunk matters; a crown may overhang
        else:
            radius = min(0.5 * min(size[0], size[1]) * scale, 1.0)
        x, y, moved_off, facing = _paths.clear_spot(location[0], location[1], radius, live)
        if not moved_off:
            return location, yaw, None
        turns = model in ("park_bench", "street_lamp") and spec.get("front") and facing is not None
        if turns:
            yaw = round(yaw_to_face(spec["front"], facing), 1)
        location = [round(x, 3), round(y, 3), location[2]]
        return location, yaw, (f"[{v.location[0]:g}, {v.location[1]:g}] was on {', '.join(moved_off)}; "
                               f"placed at the edge instead: [{location[0]:g}, {location[1]:g}]"
                               + (f", turned to face the path (yaw {yaw:g})" if turns else ""))