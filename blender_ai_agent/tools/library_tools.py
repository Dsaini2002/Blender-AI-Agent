"""
Model Library Tools
====================
Hinglish: `library/models.json` ek "sab models ki file" hai — campfire, torch, lantern, trees,
tent, rock, stool, fence, street lamp, cloud... Har model primitives + CURVES + lights ke parts
ki ek fixed recipe hai. `library.place` ek hi call mein poora model assemble karke scene mein
rakh deta hai (location, scale, rotation, colour badal sakte ho) — LLM ko har part ke coordinates
guess nahi karne padte, aur fire jaise models curves se bane tapered flames ke saath aate hain.

Naye model jodna: models.json mein ek naya entry (materials + parts + lights) daalo — code
badalne ki zaroorat nahi.
"""

import json
import math
import os
from typing import Any, Dict, List, Optional

from .base import Permission, Tool, ToolResult
from .models import ListLibraryInput, PlaceModelInput

_LIBRARY_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library", "models.json")
_cache: Dict[str, Any] = {}


def load_library(path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """models.json ko ek baar padhta hai (cache karta hai). Return: {model_name: spec}."""
    key = path or _LIBRARY_PATH
    if key not in _cache:
        with open(key, "r", encoding="utf-8") as handle:
            _cache[key] = json.load(handle)["models"]
    return _cache[key]


def find_model_by_alias(text: str) -> Optional[str]:
    """'fire' / 'aag' / 'pine tree' -> 'campfire' / 'pine_tree'. Na mile to None."""
    wanted = (text or "").strip().lower()
    for name, spec in load_library().items():
        if wanted == name or wanted.replace(" ", "_") == name or wanted in spec.get("aliases", []):
            return name
    return None


def _rotate_z(x: float, y: float, yaw: float):
    return (x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw))


def place_model(bridge, model: str, spec: Dict[str, Any], location, scale: float = 1.0,
                yaw_degrees: float = 0.0, prefix: str = "", colors: Optional[Dict[str, List[float]]] = None):
    """
    Hinglish: Ek library model ko assemble karta hai.
      - har part ki offset ko pehle `scale` se badhate hain, phir `yaw` (Z-axis) se ghumate hain,
        phir `location` mein jodte hain
      - part ki rotation mein yaw jod dete hain (Blender ka XYZ Euler = Rz*Ry*Rx, isliye exact hai)
      - Blender name collision (.001) ke liye har baar asli naam (obj.name) use hota hai
    """
    prefix = prefix or f"{model}_"
    yaw = math.radians(yaw_degrees)
    colors = colors or {}
    lx, ly, lz = location

    material_names: Dict[str, str] = {}
    for key, mat_spec in spec.get("materials", {}).items():
        color = list(colors.get(key, mat_spec["color"]))
        color = (color + [1.0])[:4] if len(color) == 3 else color
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
            # Hinglish: apne vertices/faces wala mesh (jaise tent ka triangle) — primitive nahi
            part_scale = part.get("scale", [1.0, 1.0, 1.0])
            obj = bridge.create_mesh(
                name=part_name, vertices=part["vertices"], faces=part["faces"],
                location=position, rotation=rotation,
                scale=[part_scale[0] * scale, part_scale[1] * scale, part_scale[2] * scale],
                shade_smooth=bool(part.get("smooth", False)),      # gol cheezein (character) smooth; tent jaise flat
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
            energy=light_spec.get("energy", 500.0) * scale * scale,  # bada model = zyada roshni
            size=light_spec.get("size", 0.25) * scale,
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


class LibraryPlaceTool(Tool):
    name = "library.place"
    description = (
        "Places a complete ready-made model from the model library in ONE call - far more reliable and "
        "better looking than building it from primitives. Examples: model='campfire' (stone ring, logs, "
        "glowing embers, curved tapered flame tongues, warm light), 'torch', 'lantern', 'pine_tree', "
        "'round_tree', 'bush', 'rock', 'log_seat', 'stool', 'tent', 'mushroom', 'fence', 'street_lamp', "
        "'cloud'. Origin of every model = centre of its base on the ground, +Z up. Options: location "
        "[x,y,z]; scale (uniform multiplier, 1 = natural size); yaw_degrees (turn around the vertical "
        "axis); prefix (name prefix, default '<model>_'); colors (override material colours, e.g. "
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
        if model not in library:
            resolved = find_model_by_alias(model)
            if resolved is None:
                return ToolResult.fail(f"No model named '{model}'. Available: {', '.join(sorted(library))}")
            model = resolved
        spec = library[model]

        unknown = [k for k in (validated_input.colors or {}) if k not in spec.get("materials", {})]
        if unknown:
            return ToolResult.fail(
                f"Unknown colour key(s) {unknown} for '{model}'. Valid keys: {list(spec.get('materials', {}))}"
            )

        created = place_model(
            self._bridge, model, spec, validated_input.location, validated_input.scale,
            validated_input.yaw_degrees, validated_input.prefix, validated_input.colors,
        )

        object_count = len(created["meshes"]) + len(created["curves"])
        return ToolResult.ok({
            "model": model,
            "location": list(validated_input.location),
            "scale": validated_input.scale,
            "object_count": object_count,
            "meshes": created["meshes"],
            "curves": created["curves"],
            "lights": created["lights"],
            "size_m": [round(d * validated_input.scale, 3) for d in spec.get("size", [])],
        })