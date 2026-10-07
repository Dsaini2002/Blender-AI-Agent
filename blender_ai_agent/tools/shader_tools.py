"""
material.nodes / material.recipe / render.setup
================================================
Hinglish: Agent ko "pro" shading aur finishing ki taakat dene wale tools.

  material.recipe   tayyar nuskhe: fire_flame, ember, smoke_volume, charred_wood, wood_grain, rough_stone, dirt_ground, glass, car_paint, ...
  material.nodes    koi bhi node graph (Noise -> ColorRamp -> Mix...) JSON spec se, jaanch ke saath
  render.setup      AgX/Filmic, exposure, depth of field, engine, samples, world colour, resolution — ek call mein ('cinematic', 'product', ...)
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import Permission, Tool, ToolResult
from .models import _coerce_bool, _coerce_number, _vec3, to_plain
from .shader_nodes import build_recipe, parse_material_spec, recipe_help


def _assign(bridge, material_name: str, objects: List[str]):
    assigned, missing = [], []
    for object_name in objects:
        (assigned if bridge.assign_material(object_name, material_name) else missing).append(object_name)
    return assigned, missing


def _names(value: Any, label: str) -> List[str]:
    value = to_plain(value)
    if value is None:
        return []
    if isinstance(value, str):
        value = [v for v in value.replace(",", " ").split() if v]
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{label} must be a list of object names")
    return list(value)


# =============================================================================
@dataclass
class MaterialNodesInput:
    name: str
    nodes: List[Dict[str, Any]]
    links: List[List[str]] = field(default_factory=list)
    settings: Optional[Dict[str, Any]] = None
    assign_to: List[str] = field(default_factory=list)
    replace: bool = True

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("MaterialNodesInput.name must be a non-empty string")
        self.nodes, self.links = to_plain(self.nodes), to_plain(self.links) or []
        self.settings = to_plain(self.settings) or {}
        self.assign_to = _names(self.assign_to, "MaterialNodesInput.assign_to")
        self.replace = _coerce_bool(self.replace, "MaterialNodesInput.replace")
        self.spec = parse_material_spec(self.nodes, self.links, self.settings)          # galat spec yahin pakdi jaati hai


class MaterialNodesTool(Tool):
    name = "material.nodes"
    description = (
        "Builds a procedural NODE-BASED material from a graph - for anything a plain colour cannot do: flames, smoke, wood grain, rust, marble, "
        "glass, velvet, water. nodes = [{id, type, inputs{Socket: value}, props{}, ramp[[pos,[r,g,b,a]],...] (ValToRGB only), image (TexImage)}], "
        "links = [[\"from_id.Output\", \"to_id.Input\"]] (socket name or NUMBER; use numbers for MixShader/AddShader/Math: \"mix.1\", \"mix.2\", \"m.0\"). "
        "Exactly one OutputMaterial. Types: OutputMaterial Principled Emission Transparent Diffuse Glossy Glass Translucent MixShader AddShader "
        "VolumePrincipled VolumeScatter VolumeAbsorption TexNoise TexVoronoi TexWave TexGradient TexChecker TexBrick TexImage TexCoord Mapping ValToRGB "
        "Math VectorMath SeparateXYZ CombineXYZ MapRange Clamp Bump NormalMap Displacement Fresnel LayerWeight ObjectInfo RGB Value HueSaturation Invert "
        "AmbientOcclusion LightPath. Principled inputs: 'Base Color' Metallic Roughness IOR Alpha Normal 'Emission Color' 'Emission Strength' "
        "'Coat Weight' 'Transmission Weight' 'Subsurface Weight'. Settings: surface_render_method DITHERED|BLENDED (needed for transparent/flame), "
        "use_backface_culling. assign_to = object names to apply it to. Prefer material.recipe when a recipe fits; use this to invent or tweak."
    )
    permission = Permission.SAFE_WRITE
    input_model = MaterialNodesInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: MaterialNodesInput) -> ToolResult:
        try:
            built = self._bridge.build_node_material(v.name, v.spec, v.replace)
        except ValueError as exc:
            return ToolResult.fail(str(exc))
        assigned, missing = _assign(self._bridge, built["name"], v.assign_to)
        data = dict(built, assigned_to=assigned)
        if missing:
            data["not_found"] = missing
        return ToolResult.ok(data)


# =============================================================================
@dataclass
class MaterialRecipeInput:
    name: str
    recipe: str
    params: Optional[Dict[str, Any]] = None
    assign_to: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("MaterialRecipeInput.name must be a non-empty string")
        self.params = to_plain(self.params) or {}
        if not isinstance(self.params, dict):
            raise ValueError("MaterialRecipeInput.params must be an object like {\"color\": [1, 0.2, 0, 1]}")
        self.assign_to = _names(self.assign_to, "MaterialRecipeInput.assign_to")
        self.spec = build_recipe(self.recipe, self.params)                         # unknown recipe / galat params yahin


class MaterialRecipeTool(Tool):
    name = "material.recipe"
    description = (
        "Applies a ready-made realistic procedural material. Recipes: " + recipe_help() + ". params (all optional) e.g. {\"color\": [r,g,b,a], "
        "\"strength\": 8}. assign_to = object names. Use it for EVERY main surface instead of a flat colour: fire_flame on flame meshes, ember on coals, "
        "charred_wood / wood_grain on logs and furniture, rough_stone on rocks, dirt_ground on the ground, smoke_volume on a big cube above a fire, "
        "glass on windows, car_paint on car bodies, rubber on tyres, glow on lanterns/lamps. A glowing material does not light the scene by itself: "
        "also add a light.create point light of the same colour next to it."
    )
    permission = Permission.SAFE_WRITE
    input_model = MaterialRecipeInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: MaterialRecipeInput) -> ToolResult:
        try:
            built = self._bridge.build_node_material(v.name, v.spec, True)
        except ValueError as exc:
            return ToolResult.fail(str(exc))
        assigned, missing = _assign(self._bridge, built["name"], v.assign_to)
        data = dict(built, recipe=v.recipe, assigned_to=assigned)
        if missing:
            data["not_found"] = missing
        return ToolResult.ok(data)


# =============================================================================
PRESETS = {
    "cinematic": {"engine": "eevee", "view_transform": "AgX", "look": "Medium High Contrast", "dof": True, "aperture": 2.8, "exposure": 0.0},
    "product": {"engine": "eevee", "view_transform": "AgX", "look": "None", "dof": False, "exposure": 0.3, "world_color": [0.9, 0.9, 0.92], "world_strength": 1.0},
    "outdoor": {"engine": "eevee", "view_transform": "AgX", "look": "None", "dof": False, "exposure": 0.0},
    "night": {"engine": "eevee", "view_transform": "AgX", "look": "Medium High Contrast", "dof": True, "aperture": 2.2, "exposure": 0.3,
              "world_color": [0.003, 0.005, 0.009], "world_strength": 0.08},
    "clean": {"engine": "eevee", "view_transform": "Standard", "look": "None", "dof": False, "exposure": 0.0},
}


@dataclass
class RenderSetupInput:
    preset: Optional[str] = None
    engine: Optional[str] = None
    view_transform: Optional[str] = None
    look: Optional[str] = None
    exposure: Optional[float] = None
    samples: Optional[int] = None
    denoise: Optional[bool] = None
    resolution_x: Optional[int] = None
    resolution_y: Optional[int] = None
    film_transparent: Optional[bool] = None
    dof: Optional[bool] = None
    focus_object: Optional[str] = None
    aperture: Optional[float] = None
    world_color: Optional[List[float]] = None
    world_strength: Optional[float] = None

    def __post_init__(self):
        if self.preset is not None:
            self.preset = str(self.preset).strip().lower()
            if self.preset not in PRESETS:
                raise ValueError(f"RenderSetupInput.preset must be one of {sorted(PRESETS)}")
        if self.engine is not None and str(self.engine).lower() not in ("eevee", "cycles"):
            raise ValueError("RenderSetupInput.engine must be eevee or cycles")
        for attr, integer in (("exposure", False), ("samples", True), ("resolution_x", True), ("resolution_y", True), ("aperture", False),
                              ("world_strength", False)):
            value = getattr(self, attr)
            if value is not None:
                setattr(self, attr, _coerce_number(value, f"RenderSetupInput.{attr}", integer=integer))
        for attr in ("denoise", "film_transparent", "dof"):
            value = getattr(self, attr)
            if value is not None:
                setattr(self, attr, _coerce_bool(value, f"RenderSetupInput.{attr}"))
        if self.world_color is not None:
            self.world_color = _vec3(self.world_color, "RenderSetupInput.world_color")
        if self.samples is not None and not 1 <= self.samples <= 4096:
            raise ValueError("RenderSetupInput.samples must be between 1 and 4096")
        if (self.resolution_x is None) != (self.resolution_y is None):
            raise ValueError("RenderSetupInput: give resolution_x and resolution_y together")

    def options(self) -> Dict[str, Any]:
        merged = dict(PRESETS.get(self.preset, {}))
        for key in ("engine", "view_transform", "look", "exposure", "samples", "denoise", "resolution_x", "resolution_y", "film_transparent", "dof",
                    "focus_object", "aperture", "world_color", "world_strength"):
            value = getattr(self, key)
            if value is not None:
                merged[key] = value
        if merged.get("look") in ("None", "none"):
            merged["look"] = "None"
        return merged


class RenderSetupTool(Tool):
    name = "render.setup"
    description = (
        "Finishing pass that makes any scene look professional: colour management (AgX = natural highlights, no blown-out colours), exposure, depth of "
        "field on the camera, render engine, samples, resolution, world colour/strength. preset: cinematic (AgX + contrast + DOF) | product (bright "
        "studio world) | outdoor | night (dark blue world, for fires/lanterns) | clean. Any field overrides the preset. Call it LAST, after the camera "
        "(camera.create) and lights exist; focus_object = the object the camera should keep sharp. Reports what changed and what this Blender could not do."
    )
    permission = Permission.SAFE_WRITE
    input_model = RenderSetupInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: RenderSetupInput) -> ToolResult:
        options = v.options()
        if not options:
            return ToolResult.fail("Nothing to set: give a preset (cinematic, product, outdoor, night, clean) or at least one field.")
        result = self._bridge.setup_render(**options)
        result["preset"] = v.preset
        return ToolResult.ok(result)