"""
Advanced Mesh Tools
====================
Hinglish: Mesh engine (mesh_engine.py, mesh_generators.py, mesh_script.py) ko agent ke tools mein badalta hai.

  mesh.edit     kisi bhi mesh par operators ki list / preset / formula chalao  (pighla, mudaa, toota, kaante, chhed, cut...)
  mesh.script   har vertex par chalne wala formula (jo operators se na bane, uske liye)
  mesh.lathe    profile ghuma kar bottle / vase / glass / cup / bowl / column / chess piece...
  mesh.terrain  jameen / pahaad / dunes (samtal jagah ke saath)
  mesh.sdf      shapes jod/ghata kar rock, cloud, blob, rounded boolean...
  mesh.prism    2D polygon (star, gear, ngon, rounded rect, cross, arrow, heart) extrude
  mesh.help     operators / presets / selectors / examples ki list
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .base import Permission, Tool, ToolResult
from .mesh_edit_runner import run_edit_on_parts
from .mesh_engine import (ALL_OPS, PRESET_NAMES, PRESET_ALIASES, TOPOLOGY_OPS, normalize_params, resolve_preset_name,
                          validate_ops)
from .mesh_generators import (POLYGON_KINDS, PROFILE_PRESETS, SDF_OPS, SDF_TYPES, TERRAIN_STYLES, lathe, lathe_preset,
                              polygon_points, prism, sdf_function, sdf_mesh, terrain)
from .models import _coerce_bool, _coerce_number, _vec3, to_plain


def _loc_rot_scale(obj_self):
    obj_self.location = _vec3(obj_self.location, "location")
    obj_self.rotation = _vec3(obj_self.rotation, "rotation")
    obj_self.scale = _vec3(obj_self.scale, "scale")


# =============================================================================
# mesh.edit
# =============================================================================
@dataclass
class EditMeshInput:
    """
    object_name : jis object (ya imported model) ko badalna hai
    preset      : ek shabd — melted, twisted, bent, crushed, stretched, pointed, inflated, deflated, hammered, bumpy, rough, wrinkled,
                  crumpled, eroded, aged, cracked, broken, chipped, dented, spiky, wavy, wobbly, shattered, exploded, holey, sliced
                  (synonyms bhi chalte hain: "pighla hua", "toota", "kaante wala"...)
    strength    : 0.02-1.0 (kitna zyada), region: top/bottom/left/right/front/back/all (damage presets ke liye)
    ops         : operators ki list — [{"op": "twist", "angle": 90, "select": "top"}, ...]  (mesh.help se poori list)
    code        : har vertex par chalne wala formula (mesh.script jaisa), ops ke baad chalta hai
    select      : preset/code par lagne wala selection (warna poora object)
    """
    object_name: str
    preset: Optional[str] = None
    strength: float = 0.5
    region: str = "top"
    select: Optional[Any] = None
    seed: int = 1
    detail: Optional[int] = None
    ops: Optional[List[Dict[str, Any]]] = None
    code: Optional[str] = None
    final_ops: List[Dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("EditMeshInput.object_name must be a non-empty string")
        if self.preset is None and not self.ops and not self.code:
            raise ValueError("EditMeshInput needs at least one of: preset, ops, code (see mesh.help)")

        self.strength = _coerce_number(self.strength, "EditMeshInput.strength")
        self.seed = _coerce_number(self.seed, "EditMeshInput.seed", integer=True)
        self.region = str(self.region)
        if self.detail is not None:
            self.detail = _coerce_number(self.detail, "EditMeshInput.detail", integer=True)
            if not 0 <= self.detail <= 2:
                raise ValueError("EditMeshInput.detail must be 0, 1 or 2")

        select = to_plain(self.select)
        ops: List[Dict[str, Any]] = []
        if self.preset is not None:
            if resolve_preset_name(self.preset) is None:
                raise ValueError(f"EditMeshInput.preset '{self.preset}' is unknown. Presets: {', '.join(PRESET_NAMES)}")
            op = {"op": "preset", "name": self.preset, "strength": self.strength, "region": self.region, "seed": self.seed}
            if select is not None:
                op["select"] = select
            if self.detail is not None:
                op["detail"] = self.detail
            ops.append(op)
        if self.ops:
            raw = to_plain(self.ops)
            if isinstance(raw, dict):
                raw = [raw]
            ops.extend(raw)
        if self.code:
            script = {"op": "script", "code": str(self.code), "seed": self.seed}
            if select is not None:
                script["select"] = select
            ops.append(script)
        self.final_ops = validate_ops(ops)


class MeshEditTool(Tool):
    name = "mesh.edit"
    description = (
        "General mesh editor for ANY change to an existing object or imported model: melted, twisted, bent, squashed, stretched, "
        "pointed, inflated, bumpy, rough, wrinkled, eroded, aged, cracked, broken, chipped, dented, spiky, wavy, shattered, exploded, "
        "holey, cut in half... Easiest: preset='<word>' (strength 0.1 slight, 0.5 medium, 1.0 extreme; region top/bottom/left/right/"
        "front/back/all for broken/chipped/dented). For anything custom combine operators in `ops` (a list, run in order): move scale "
        "rotate twist bend taper stretch bulge inflate noise wave melt spikes smooth crack holes erode damage script + subdivide cut "
        "extrude shatter - each can have a `select` (\"top\", {\"sphere\":..}, {\"noise\":..}, {\"facing\":..}, and/or/not...). "
        "Examples: twist the upper half 90 degrees: ops=[{\"op\":\"twist\",\"angle\":90,\"select\":\"top\"}]; leaning tower: "
        "ops=[{\"op\":\"bend\",\"angle\":25}]; cheese holes: ops=[{\"op\":\"holes\",\"count\":8,\"radius\":0.07}]. For a formula over "
        "every vertex pass `code` (see mesh.script). Call mesh.help for the full list. NEVER tell the user a change is impossible: "
        "pick a preset or compose operators. Works on a mesh or an imported model's root; keeps UVs/materials when it only moves vertices."
    )
    permission = Permission.SAFE_WRITE
    input_model = EditMeshInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: EditMeshInput) -> ToolResult:
        snapshot = self._bridge.snapshot_mesh(validated_input.object_name)
        if snapshot is None:
            return ToolResult.fail(f"Object '{validated_input.object_name}' not found, or it has no mesh to edit.")

        results, notes = run_edit_on_parts(snapshot["parts"], validated_input.final_ops, validated_input.seed)
        summary = self._bridge.apply_mesh_edit(results)
        return ToolResult.ok({
            "object": snapshot["root"], "operators": [o["op"] if o["op"] != "preset" else f"preset:{o['name']}"
                                                      for o in validated_input.final_ops],
            "notes": notes, **summary,
        })


# =============================================================================
# mesh.script
# =============================================================================
@dataclass
class ScriptMeshInput:
    """object_name + code (har vertex par chalne wala formula) + optional select."""
    object_name: str
    code: str
    select: Optional[Any] = None
    seed: int = 1
    final_ops: List[Dict[str, Any]] = field(default_factory=list, init=False, repr=False)

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("ScriptMeshInput.object_name must be a non-empty string")
        if not self.code or not isinstance(self.code, str):
            raise ValueError("ScriptMeshInput.code must be a non-empty string")
        self.seed = _coerce_number(self.seed, "ScriptMeshInput.seed", integer=True)
        op = {"op": "script", "code": self.code, "seed": self.seed}
        select = to_plain(self.select)
        if select is not None:
            op["select"] = select
        self.final_ops = validate_ops([op])


class MeshScriptTool(Tool):
    name = "mesh.script"
    description = (
        "Runs a short formula on EVERY vertex of an object - use when no operator/preset fits. Pure math, safe sandbox. Inputs "
        "per vertex: x y z (world), u v w (0..1 inside the bounding box), nx ny nz (normal), i, n, size, cx cy cz, minx..maxz. "
        "Set dx dy dz (displacement) or reassign x y z; set remove=1 to delete the faces at that vertex. Functions: sin cos tan "
        "asin acos atan atan2 sqrt exp log hypot floor ceil abs min max pow radians degrees sign clamp lerp smoothstep step fract "
        "mod noise fbm ridged rand; constants pi tau e. Allowed: assignments, if/elif/else, `for k in range(<=32)`. No imports, "
        "attributes, while, def. Example (ripples): dz = 0.03 * size * sin(u * 20 + v * 14). Example (flare the top): "
        "s = 1 + 0.6 * smoothstep(0.5, 1.0, w); dx = (x - cx) * (s - 1); dy = (y - cy) * (s - 1). Optional `select` limits where "
        "it applies (\"top\", {\"sphere\": {...}} ...)."
    )
    permission = Permission.SAFE_WRITE
    input_model = ScriptMeshInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: ScriptMeshInput) -> ToolResult:
        snapshot = self._bridge.snapshot_mesh(validated_input.object_name)
        if snapshot is None:
            return ToolResult.fail(f"Object '{validated_input.object_name}' not found, or it has no mesh to edit.")
        results, notes = run_edit_on_parts(snapshot["parts"], validated_input.final_ops, validated_input.seed)
        summary = self._bridge.apply_mesh_edit(results)
        return ToolResult.ok({"object": snapshot["root"], "notes": notes, **summary})


# =============================================================================
# Generators (naye objects)
# =============================================================================
def _create(bridge, name, vertices, faces, location, rotation, scale, smooth):
    obj = bridge.create_mesh(name=name, vertices=vertices, faces=faces, location=location, rotation=rotation,
                             scale=scale, shade_smooth=smooth)
    return {"name": obj.name, "vertex_count": len(vertices), "face_count": len(faces), "location": list(obj.location)}


@dataclass
class LatheInput:
    name: str
    preset: Optional[str] = None
    profile: Optional[List[List[float]]] = None
    height: float = 1.0
    radius: float = 0.25
    thickness: Optional[float] = None
    segments: int = 32
    angle_degrees: float = 360.0
    shade_smooth: bool = True
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("LatheInput.name must be a non-empty string")
        if self.preset is None and not self.profile:
            raise ValueError(f"LatheInput needs `preset` ({', '.join(sorted(PROFILE_PRESETS))}) or `profile` [[r, z], ...]")
        self.height = _coerce_number(self.height, "LatheInput.height")
        self.radius = _coerce_number(self.radius, "LatheInput.radius")
        if self.height <= 0 or self.radius <= 0:
            raise ValueError("LatheInput.height and radius must be positive")
        if self.thickness is not None:
            self.thickness = _coerce_number(self.thickness, "LatheInput.thickness")
            if not 0 <= self.thickness <= 0.9:
                raise ValueError("LatheInput.thickness must be between 0 and 0.9 (fraction of the radius)")
        self.segments = _coerce_number(self.segments, "LatheInput.segments", integer=True)
        if not 3 <= self.segments <= 256:
            raise ValueError("LatheInput.segments must be between 3 and 256")
        self.angle_degrees = _coerce_number(self.angle_degrees, "LatheInput.angle_degrees")
        self.shade_smooth = _coerce_bool(self.shade_smooth, "LatheInput.shade_smooth")
        if self.preset is not None:
            key = str(self.preset).strip().lower().replace(" ", "_")
            if key not in PROFILE_PRESETS:
                raise ValueError(f"LatheInput.preset must be one of {sorted(PROFILE_PRESETS)}, got '{self.preset}'")
            self.preset = key
        else:
            raw = to_plain(self.profile)
            if not isinstance(raw, list) or len(raw) < 2:
                raise ValueError("LatheInput.profile must be a list of at least 2 points [[r, z], ...]")
            cleaned = []
            for point in raw:
                coords = _vec3(list(point) + [0.0], "LatheInput.profile[]")[:2] if isinstance(point, (list, tuple)) and len(point) == 2 else None
                if coords is None:
                    raise ValueError("each LatheInput.profile point must be [r, z]")
                cleaned.append([float(point[0]), float(point[1])])
            self.profile = cleaned
        _loc_rot_scale(self)


class MeshLatheTool(Tool):
    name = "mesh.lathe"
    description = (
        "Creates a round object by spinning a 2D profile around the vertical axis. Easiest: preset = bottle, vase, wine_glass, "
        "cup, mug, bowl, column, chess_pawn, lamp, barrel, candle, bell (with height, radius in metres; hollow containers get a "
        "wall - `thickness` is a fraction of the radius, 0 = solid). Custom: profile = [[r, z], ...] from the bottom up, e.g. a "
        "goblet [[0,0],[0.3,0],[0.05,0.1],[0.05,0.4],[0.3,0.6],[0.3,0.8]] (add thickness to make it hollow). angle_degrees < 360 "
        "gives a partial revolve. Colour it with material.create + material.assign."
    )
    permission = Permission.SAFE_WRITE
    input_model = LatheInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: LatheInput) -> ToolResult:
        if v.preset is not None:
            vertices, faces = lathe_preset(v.preset, v.height, v.radius, v.thickness, v.segments)
            if abs(v.angle_degrees) < 359.999:
                from .mesh_generators import PROFILE_PRESETS as presets
                profile, default_hollow = presets[v.preset]
                hollow = (default_hollow if v.thickness is None else v.thickness) * v.radius
                vertices, faces = lathe([(r * v.radius, z * v.height) for r, z in profile], v.segments, v.angle_degrees, hollow)
        else:
            hollow = (v.thickness or 0.0) * v.radius
            vertices, faces = lathe(v.profile, v.segments, v.angle_degrees, hollow)
        return ToolResult.ok(_create(self._bridge, v.name, vertices, faces, v.location, v.rotation, v.scale, v.shade_smooth))


@dataclass
class TerrainInput:
    name: str
    size: Any = 10.0
    resolution: int = 40
    height: float = 1.5
    noise_scale: float = 3.0
    octaves: int = 4
    seed: int = 1
    style: str = "hills"
    flat_radius: float = 0.0
    edge_fade: float = 0.0
    shade_smooth: bool = True
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("TerrainInput.name must be a non-empty string")
        size = to_plain(self.size)
        if isinstance(size, (list, tuple)):
            if len(size) != 2:
                raise ValueError("TerrainInput.size must be a number or [size_x, size_y]")
            self.size = [_coerce_number(size[0], "TerrainInput.size"), _coerce_number(size[1], "TerrainInput.size")]
        else:
            value = _coerce_number(size, "TerrainInput.size")
            self.size = [value, value]
        if not all(0.1 <= s <= 2000 for s in self.size):
            raise ValueError("TerrainInput.size must be between 0.1 and 2000 metres")
        self.resolution = _coerce_number(self.resolution, "TerrainInput.resolution", integer=True)
        if not 4 <= self.resolution <= 220:
            raise ValueError("TerrainInput.resolution must be between 4 and 220")
        self.height = _coerce_number(self.height, "TerrainInput.height")
        self.noise_scale = _coerce_number(self.noise_scale, "TerrainInput.noise_scale")
        self.octaves = _coerce_number(self.octaves, "TerrainInput.octaves", integer=True)
        self.seed = _coerce_number(self.seed, "TerrainInput.seed", integer=True)
        self.flat_radius = _coerce_number(self.flat_radius, "TerrainInput.flat_radius")
        self.edge_fade = _coerce_number(self.edge_fade, "TerrainInput.edge_fade")
        self.style = str(self.style).strip().lower()
        if self.style not in TERRAIN_STYLES:
            raise ValueError(f"TerrainInput.style must be one of {list(TERRAIN_STYLES)}, got '{self.style}'")
        self.shade_smooth = _coerce_bool(self.shade_smooth, "TerrainInput.shade_smooth")
        _loc_rot_scale(self)


class MeshTerrainTool(Tool):
    name = "mesh.terrain"
    description = (
        "Creates ground / landscape: style hills, mountains, dunes, plateau or flat; size (metres, number or [x, y]); height of the "
        "relief; noise_scale (more = more bumps); resolution (grid, 40 default, up to 220). flat_radius 0.3-0.6 keeps a level area "
        "in the middle (for a campsite, house, road); edge_fade 0.2-0.5 flattens the border so it blends into a plane. Z is up, "
        "centred on the origin. Colour it with material.create + material.assign."
    )
    permission = Permission.SAFE_WRITE
    input_model = TerrainInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: TerrainInput) -> ToolResult:
        vertices, faces = terrain(v.size[0], v.size[1], v.resolution, v.height, v.noise_scale, v.octaves, v.seed, v.style,
                                  v.flat_radius, v.edge_fade)
        return ToolResult.ok(_create(self._bridge, v.name, vertices, faces, v.location, v.rotation, v.scale, v.shade_smooth))


@dataclass
class SdfInput:
    name: str
    shapes: List[Dict[str, Any]]
    resolution: int = 40
    roughness: float = 0.0
    noise_scale: float = 4.0
    seed: int = 1
    bounds: Optional[List[float]] = None
    shade_smooth: bool = True
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("SdfInput.name must be a non-empty string")
        raw = to_plain(self.shapes)
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list) or not raw or not all(isinstance(s, dict) for s in raw):
            raise ValueError("SdfInput.shapes must be a non-empty list of shape objects, e.g. [{\"type\": \"sphere\", \"radius\": 0.5}]")
        if len(raw) > 32:
            raise ValueError("SdfInput.shapes: at most 32 shapes")
        self.shapes = [normalize_params(shape) for shape in raw]      # {"x":..} / "1,2,3" / "0.5" sab saaf
        try:
            sdf_function(self.shapes)                  # type / op / numbers ki jaanch
        except (TypeError, KeyError, IndexError) as exc:
            raise ValueError(f"SdfInput.shapes has a malformed shape ({exc}); vectors must be [x, y, z]") from exc
        self.resolution = _coerce_number(self.resolution, "SdfInput.resolution", integer=True)
        if not 8 <= self.resolution <= 90:
            raise ValueError("SdfInput.resolution must be between 8 and 90")
        self.roughness = _coerce_number(self.roughness, "SdfInput.roughness")
        self.noise_scale = _coerce_number(self.noise_scale, "SdfInput.noise_scale")
        self.seed = _coerce_number(self.seed, "SdfInput.seed", integer=True)
        if self.bounds is not None:
            b = [float(c) for c in to_plain(self.bounds)]
            if len(b) != 6:
                raise ValueError("SdfInput.bounds must be [minx, miny, minz, maxx, maxy, maxz]")
            self.bounds = b
        self.shade_smooth = _coerce_bool(self.shade_smooth, "SdfInput.shade_smooth")
        _loc_rot_scale(self)


class MeshSdfTool(Tool):
    name = "mesh.sdf"
    description = (
        "Builds organic / blended solids from simple shapes combined like boolean + smooth blending (rocks, clouds, blobs, creature "
        "bodies, rounded boxes, bowls, a cube with a sphere cut out...). shapes = list, applied in order; each: {\"type\": sphere|"
        "ellipsoid|box|capsule|cylinder|torus|cone (flat base, radius + radius_top + height)|round_cone|plane, \"center\": [x,y,z], size/radius/radii/height/major/minor/a/b..., "
        "\"rotation\": [rx,ry,rz degrees], \"rounding\": r, \"op\": union|smooth_union|subtract|intersect, \"k\": blend size}. "
        "Examples: snowman = [{\"type\":\"sphere\",\"radius\":0.5,\"center\":[0,0,0.5]},{\"type\":\"sphere\",\"radius\":0.35,"
        "\"center\":[0,0,1.2],\"op\":\"smooth_union\",\"k\":0.1}]; hollow bowl = sphere radius 0.5 then {\"type\":\"sphere\","
        "\"radius\":0.45,\"center\":[0,0,0.1],\"op\":\"subtract\"}. roughness 0.02-0.1 adds natural bumpiness (rocks). resolution "
        "40 default (max 90; higher = smoother, slower)."
    )
    permission = Permission.SAFE_WRITE
    input_model = SdfInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: SdfInput) -> ToolResult:
        vertices, faces = sdf_mesh(v.shapes, v.resolution, v.bounds, v.roughness, v.noise_scale, v.seed)
        if not faces:
            return ToolResult.fail("The shapes produced no surface (empty result). Check sizes, centers and the subtract/intersect order.")
        return ToolResult.ok(_create(self._bridge, v.name, vertices, faces, v.location, v.rotation, v.scale, v.shade_smooth))


@dataclass
class PrismInput:
    name: str
    kind: Optional[str] = None
    polygon: Optional[List[List[float]]] = None
    sides: int = 6
    radius: float = 0.5
    inner_radius: float = 0.0
    width: float = 1.0
    depth: float = 1.0
    corner: float = 0.15
    height: float = 0.2
    taper: float = 1.0
    cap: bool = True
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("PrismInput.name must be a non-empty string")
        if self.kind is None and not self.polygon:
            raise ValueError(f"PrismInput needs `kind` ({', '.join(POLYGON_KINDS)}) or `polygon` [[x, y], ...]")
        for attr in ("radius", "inner_radius", "width", "depth", "corner", "height", "taper"):
            setattr(self, attr, _coerce_number(getattr(self, attr), f"PrismInput.{attr}"))
        self.sides = _coerce_number(self.sides, "PrismInput.sides", integer=True)
        if self.height <= 0 or self.taper < 0:
            raise ValueError("PrismInput.height must be positive and taper must not be negative")
        self.cap = _coerce_bool(self.cap, "PrismInput.cap")
        if self.kind is not None:
            self.kind = str(self.kind).strip().lower().replace(" ", "_")
            if self.kind not in POLYGON_KINDS:
                raise ValueError(f"PrismInput.kind must be one of {list(POLYGON_KINDS)}, got '{self.kind}'")
        else:
            raw = to_plain(self.polygon)
            if not isinstance(raw, list) or len(raw) < 3 or not all(isinstance(p, (list, tuple)) and len(p) == 2 for p in raw):
                raise ValueError("PrismInput.polygon must be a list of at least 3 points [[x, y], ...]")
            self.polygon = [[float(p[0]), float(p[1])] for p in raw]
        _loc_rot_scale(self)


class MeshPrismTool(Tool):
    name = "mesh.prism"
    description = (
        "Extrudes a flat 2D shape upward: kind = ngon (sides, radius), star (sides = points, radius, inner_radius), gear (sides = "
        "teeth, radius = tooth tip, inner_radius = root), rounded_rect (width, depth, corner), cross (width, inner_radius = arm "
        "thickness), arrow, heart - or a custom `polygon` [[x, y], ...]. height = thickness; taper < 1 narrows the top (frustum, "
        "badge, button), taper > 1 widens it. Good for gears, signs, tiles, coins, stars, buttons."
    )
    permission = Permission.SAFE_WRITE
    input_model = PrismInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: PrismInput) -> ToolResult:
        points = v.polygon if v.polygon else polygon_points(v.kind, v.sides, v.radius, v.inner_radius, v.width, v.depth, v.corner)
        vertices, faces = prism(points, v.height, v.taper, v.cap)
        return ToolResult.ok(_create(self._bridge, v.name, vertices, faces, v.location, v.rotation, v.scale, False))


# =============================================================================
# mesh.help
# =============================================================================
@dataclass
class MeshHelpInput:
    topic: str = "all"

    def __post_init__(self):
        self.topic = str(self.topic or "all").strip().lower()
        if self.topic not in ("all", "operators", "presets", "selectors", "generators", "examples"):
            raise ValueError("MeshHelpInput.topic must be one of: all, operators, presets, selectors, generators, examples")


_HELP = {
    "operators": {
        "move": "offset [x,y,z] (fraction of object size; absolute:true for metres)",
        "scale": "factor (number or [x,y,z]), pivot center|base|top|selection|[rel x,y,z]",
        "rotate": "angle (degrees), axis x|y|z, pivot",
        "twist": "angle (degrees across the object), axis (z)",
        "bend": "angle (degrees), axis (long axis, z), direction (x)",
        "taper": "start/end cross-section scale along axis (z): start 1, end 0.3",
        "stretch": "factor, axis, pivot, preserve_volume",
        "bulge": "amount (-0.9..5), axis, shape belly|ends",
        "inflate": "amount (-0.5..0.5 of size) along normals",
        "noise": "amplitude, scale, octaves, mode normal|xyz|x|y|z, ridged, seed",
        "wave": "amplitude, wavelength, axis (travel), displace normal|x|y|z, phase",
        "melt": "amount 0..1, spread 0..3 (top sags and pools at the bottom)",
        "spikes": "count, length, radius, seed",
        "smooth": "iterations, factor",
        "crack": "count, depth, width, length, jaggedness, seed",
        "holes": "count, radius (or fraction) - removes faces",
        "erode": "threshold, scale, amount - eats away patches",
        "damage": "style broken|chipped|dented|rough, region, portion, strength",
        "script": "code (per-vertex formula, see mesh.script)",
        "subdivide": "levels 1-3 (adds detail inside `select`)",
        "cut": "axis x|y|z, at 0..1 (or value in metres), keep below|above, cap true|false - slices the object",
        "extrude": "amount (fraction of size) - pushes selected faces out/in",
        "shatter": "pieces, spread, rotate - splits into separate shards",
    },
    "selectors": [
        "\"all\" | \"top\" | \"bottom\" | \"left\" | \"right\" | \"front\" | \"back\" | \"up_facing\" | \"down_facing\" | \"sides\"  (neck, lid, rim = top; base = bottom)",
        "{\"region\": \"top\", \"portion\": 0.3}",
        "{\"sphere\": {\"center\": [0.5, 0.5, 1.0], \"radius\": 0.25}}   center is 0..1 inside the bounding box, radius = fraction of size",
        "{\"box\": {\"min\": [0, 0, 0.6], \"max\": [1, 1, 1]}}   {\"slab\": {\"axis\": \"z\", \"from\": 0.4, \"to\": 0.6}}",
        "{\"noise\": {\"scale\": 3, \"threshold\": 0.5}}  patches   {\"random\": {\"fraction\": 0.2}}   {\"facing\": {\"direction\": \"up\"}}",
        "{\"and\": [sel, sel]}  {\"or\": [sel, sel]}  {\"not\": sel}   any selector accepts \"falloff\": smooth|linear|sharp|none, \"invert\": true",
    ],
    "examples": [
        "melted candle: preset='melted', strength 0.6",
        "leaning tower: ops=[{op:'bend', angle:20, axis:'z', direction:'x'}]",
        "dent in the middle: ops=[{op:'damage', style:'dented', region:'all'}] or ops=[{op:'inflate', amount:-0.08, select:{sphere:{center:[0.5,0.5,0.5], radius:0.2}}}]",
        "moss on top surfaces: ops=[{op:'noise', amplitude:0.02, scale:8, select:{facing:{direction:'up'}}}]",
        "tooth-edge top: ops=[{op:'subdivide', levels:2, select:'top'}, {op:'wave', amplitude:0.04, wavelength:0.08, axis:'x', displace:'z', select:'top'}]",
        "cut in half with cap: preset='sliced'  or ops=[{op:'cut', axis:'z', at:0.5, keep:'below'}]",
        "custom: code='dz = 0.03 * size * sin(u * 20 + v * 14)'",
    ],
}


class MeshHelpTool(Tool):
    name = "mesh.help"
    description = (
        "Lists everything the mesh editor can do: operators, presets, selectors, generators (lathe, terrain, sdf, prism) and "
        "worked examples. Call it when a user asks for a change to an object and you are unsure how to express it - then use "
        "mesh.edit / mesh.script / mesh.lathe / mesh.sdf. topic: all | operators | presets | selectors | generators | examples."
    )
    permission = Permission.READ_ONLY
    input_model = MeshHelpInput

    def __init__(self, bridge=None):
        self._bridge = bridge

    def run(self, v: MeshHelpInput) -> ToolResult:
        data: Dict[str, Any] = {}
        if v.topic in ("all", "operators"):
            data["operators"] = _HELP["operators"]
            data["topology_operators"] = sorted(TOPOLOGY_OPS)
        if v.topic in ("all", "presets"):
            data["presets"] = list(PRESET_NAMES)
            data["preset_synonyms_examples"] = dict(list(PRESET_ALIASES.items())[:24])
        if v.topic in ("all", "selectors"):
            data["selectors"] = _HELP["selectors"]
        if v.topic in ("all", "generators"):
            data["generators"] = {
                "mesh.lathe": f"presets: {', '.join(sorted(PROFILE_PRESETS))} or profile [[r,z],...]",
                "mesh.terrain": f"styles: {', '.join(TERRAIN_STYLES)}",
                "mesh.sdf": f"shape types: {', '.join(SDF_TYPES)}; ops: {', '.join(SDF_OPS)}",
                "mesh.prism": f"kinds: {', '.join(POLYGON_KINDS)} or a polygon",
                "mesh.create": "raw vertices + faces", "curve.create": "tubes / ropes / tapered shapes",
            }
        if v.topic in ("all", "examples"):
            data["examples"] = _HELP["examples"]
        return ToolResult.ok(data)