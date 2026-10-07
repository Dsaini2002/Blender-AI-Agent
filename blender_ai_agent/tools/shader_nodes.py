"""
shader_nodes.py
================
Hinglish: Node-based (procedural) materials ka SAFE builder-spec + recipes. Pure Python (bpy nahi) — spec ki jaanch yahan, node banana bridge mein.

Kyun: sirf rang/metallic/roughness se kaam ki cheezein (aag, dhuan, lakdi ke daane, patthar, sheesha, car paint) asli nahi lagti. Achhe artists
Noise -> ColorRamp -> Mix(Emission, Transparent) jaise node graphs banate hain. Ab agent bhi bana sakta hai:

    material_nodes(name="Flame", nodes=[...], links=[["noise.Fac", "ramp.Fac"], ...])      # kuch bhi
    material_recipe(name="Flame", recipe="fire_flame", params={"color": [1, .1, 0, 1]})    # tayyar nuskhe

Spec:
  nodes  : [{"id": "n1", "type": "TexNoise", "inputs": {"Scale": 2.4}, "props": {"noise_dimensions": "3D"}, "ramp": [[pos, [r,g,b,a]], ...],
             "image": "C:/x.png", "colorspace": "Non-Color", "location": [x, y]}]
  links  : [["from_id.OutputSocket", "to_id.InputSocket"]]   (socket naam ya number; Mix/Add shader aur Math mein number use karo: "mix.1", "mix.2")
  settings: {"surface_render_method": "DITHERED" | "BLENDED", "use_backface_culling": false, "displacement_method": "BUMP"}
"""

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

MAX_NODES = 80
MAX_LINKS = 160

NODE_TYPES: Dict[str, str] = {
    "OutputMaterial": "ShaderNodeOutputMaterial", "Principled": "ShaderNodeBsdfPrincipled", "Emission": "ShaderNodeEmission",
    "Transparent": "ShaderNodeBsdfTransparent", "Diffuse": "ShaderNodeBsdfDiffuse", "Glossy": "ShaderNodeBsdfGlossy",
    "Glass": "ShaderNodeBsdfGlass", "Translucent": "ShaderNodeBsdfTranslucent", "MixShader": "ShaderNodeMixShader",
    "AddShader": "ShaderNodeAddShader", "VolumePrincipled": "ShaderNodeVolumePrincipled", "VolumeScatter": "ShaderNodeVolumeScatter",
    "VolumeAbsorption": "ShaderNodeVolumeAbsorption", "TexNoise": "ShaderNodeTexNoise", "TexVoronoi": "ShaderNodeTexVoronoi",
    "TexWave": "ShaderNodeTexWave", "TexGradient": "ShaderNodeTexGradient", "TexChecker": "ShaderNodeTexChecker",
    "TexBrick": "ShaderNodeTexBrick", "TexImage": "ShaderNodeTexImage", "TexCoord": "ShaderNodeTexCoord", "Mapping": "ShaderNodeMapping",
    "ValToRGB": "ShaderNodeValToRGB", "Math": "ShaderNodeMath", "VectorMath": "ShaderNodeVectorMath", "SeparateXYZ": "ShaderNodeSeparateXYZ",
    "CombineXYZ": "ShaderNodeCombineXYZ", "MapRange": "ShaderNodeMapRange", "Clamp": "ShaderNodeClamp", "Bump": "ShaderNodeBump",
    "NormalMap": "ShaderNodeNormalMap", "Displacement": "ShaderNodeDisplacement", "Fresnel": "ShaderNodeFresnel",
    "LayerWeight": "ShaderNodeLayerWeight", "ObjectInfo": "ShaderNodeObjectInfo", "RGB": "ShaderNodeRGB", "Value": "ShaderNodeValue",
    "HueSaturation": "ShaderNodeHueSaturation", "Invert": "ShaderNodeInvert", "AmbientOcclusion": "ShaderNodeAmbientOcclusion",
    "LightPath": "ShaderNodeLightPath",
}
_IDNAMES = set(NODE_TYPES.values())

# Node par set ho sakne wale properties (aur unki allowed values ya None = koi bhi simple value)
ALLOWED_PROPS = {"operation", "blend_type", "noise_dimensions", "noise_type", "normalize", "distribution", "subsurface_method", "interpolation",
                 "data_type", "wave_type", "wave_profile", "bands_direction", "rings_direction", "voronoi_dimensions", "feature", "distance",
                 "use_clamp", "clamp", "gradient_type", "projection", "extension", "invert", "space", "vector_type", "mapping_type",
                 "checker_size", "offset", "squash", "label"}
ALLOWED_SETTINGS = {"surface_render_method": ("DITHERED", "BLENDED"), "use_backface_culling": (True, False),
                    "displacement_method": ("BUMP", "DISPLACEMENT", "BOTH"), "use_transparent_shadow": (True, False)}

# Static socket table (typos pakadne ke liye; list mein na ho to sirf Blender ke andar jaanch). Numbers (indices) hamesha allowed.
SOCKETS: Dict[str, Tuple[List[str], List[str]]] = {
    "OutputMaterial": (["Surface", "Volume", "Displacement"], []),
    "Principled": (["Base Color", "Metallic", "Roughness", "IOR", "Alpha", "Normal", "Subsurface Weight", "Subsurface Radius", "Subsurface Scale",
                    "Specular IOR Level", "Specular Tint", "Anisotropic", "Transmission Weight", "Coat Weight", "Coat Roughness", "Coat IOR",
                    "Coat Tint", "Sheen Weight", "Sheen Roughness", "Emission Color", "Emission Strength"], ["BSDF"]),
    "Emission": (["Color", "Strength"], ["Emission"]), "Transparent": (["Color"], ["BSDF"]),
    "Diffuse": (["Color", "Roughness", "Normal"], ["BSDF"]), "Glossy": (["Color", "Roughness", "Normal"], ["BSDF"]),
    "Glass": (["Color", "Roughness", "IOR", "Normal"], ["BSDF"]), "Translucent": (["Color", "Normal"], ["BSDF"]),
    "MixShader": (["Fac", "1", "2"], ["Shader"]), "AddShader": (["1", "2"], ["Shader"]),
    "VolumePrincipled": (["Color", "Color Attribute", "Density", "Density Attribute", "Anisotropy", "Absorption Color", "Emission Strength",
                          "Emission Color", "Blackbody Intensity", "Blackbody Tint", "Temperature", "Temperature Attribute"], ["Volume"]),
    "VolumeScatter": (["Color", "Density", "Anisotropy"], ["Volume"]), "VolumeAbsorption": (["Color", "Density"], ["Volume"]),
    "TexNoise": (["Vector", "W", "Scale", "Detail", "Roughness", "Lacunarity", "Offset", "Gain", "Distortion"], ["Fac", "Color"]),
    "TexVoronoi": (["Vector", "W", "Scale", "Detail", "Roughness", "Lacunarity", "Smoothness", "Exponent", "Randomness"], ["Distance", "Color", "Position", "W", "Radius"]),
    "TexWave": (["Vector", "Scale", "Distortion", "Detail", "Detail Scale", "Detail Roughness", "Phase Offset"], ["Color", "Fac"]),
    "TexGradient": (["Vector"], ["Color", "Fac"]), "TexChecker": (["Vector", "Color1", "Color2", "Scale"], ["Color", "Fac"]),
    "TexBrick": (["Vector", "Color1", "Color2", "Mortar", "Scale", "Mortar Size", "Mortar Smooth", "Bias", "Brick Width", "Row Height"], ["Color", "Fac"]),
    "TexImage": (["Vector"], ["Color", "Alpha"]),
    "TexCoord": ([], ["Generated", "Normal", "UV", "Object", "Camera", "Window", "Reflection"]),
    "Mapping": (["Vector", "Location", "Rotation", "Scale"], ["Vector"]), "ValToRGB": (["Fac"], ["Color", "Alpha"]),
    "Math": (["0", "1", "2"], ["Value"]), "VectorMath": (["0", "1", "2", "Scale"], ["Vector", "Value"]),
    "SeparateXYZ": (["Vector"], ["X", "Y", "Z"]), "CombineXYZ": (["X", "Y", "Z"], ["Vector"]),
    "MapRange": (["Value", "From Min", "From Max", "To Min", "To Max", "Steps"], ["Result"]), "Clamp": (["Value", "Min", "Max"], ["Result"]),
    "Bump": (["Strength", "Distance", "Height", "Normal"], ["Normal"]), "NormalMap": (["Strength", "Color"], ["Normal"]),
    "Displacement": (["Height", "Midlevel", "Scale", "Normal"], ["Displacement"]), "Fresnel": (["IOR", "Normal"], ["Fac"]),
    "LayerWeight": (["Blend", "Normal"], ["Fresnel", "Facing"]), "ObjectInfo": ([], ["Location", "Color", "Alpha", "Object Index", "Material Index", "Random"]),
    "RGB": ([], ["Color"]), "Value": ([], ["Value"]), "HueSaturation": (["Hue", "Saturation", "Value", "Fac", "Color"], ["Color"]),
    "Invert": (["Fac", "Color"], ["Color"]), "AmbientOcclusion": (["Color", "Distance", "Normal"], ["Color", "AO"]),
    "LightPath": ([], ["Is Camera Ray", "Is Shadow Ray", "Is Diffuse Ray", "Is Glossy Ray", "Is Singular Ray", "Is Reflection Ray",
                       "Is Transmission Ray", "Ray Length", "Ray Depth", "Transparent Depth", "Transmission Depth"]),
}


@dataclass
class NodeSpec:
    id: str
    type: str                                   # NODE_TYPES ka short naam
    idname: str
    inputs: Dict[str, Any] = field(default_factory=dict)
    props: Dict[str, Any] = field(default_factory=dict)
    ramp: Optional[List[Tuple[float, List[float]]]] = None
    image: Optional[str] = None
    colorspace: Optional[str] = None
    location: Optional[Tuple[float, float]] = None


@dataclass
class MaterialSpec:
    nodes: List[NodeSpec]
    links: List[Tuple[str, str, str, str]]       # from_id, from_socket, to_id, to_socket
    settings: Dict[str, Any] = field(default_factory=dict)


def _short_type(value: str) -> Tuple[str, str]:
    text = str(value).strip()
    if text in NODE_TYPES:
        return text, NODE_TYPES[text]
    for short, idname in NODE_TYPES.items():
        if text == idname or text.lower().replace("shadernode", "") == short.lower():
            return short, idname
    raise ValueError(f"unknown node type '{value}'. Types: {', '.join(sorted(NODE_TYPES))}")


def _coerce_value(value: Any, where: str) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value) if not isinstance(value, int) else value
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        if not 1 <= len(value) <= 4 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
            raise ValueError(f"{where}: a vector/colour must be 1-4 numbers, got {value!r}")
        return [float(v) for v in value]
    raise ValueError(f"{where}: unsupported value {value!r}")


def _split_socket(ref: Any, where: str) -> Tuple[str, str]:
    text = str(ref)
    if "." not in text:
        raise ValueError(f"{where}: link end '{text}' must look like 'node_id.Socket' (socket name or number)")
    node_id, socket = text.split(".", 1)
    return node_id.strip(), socket.strip()


def parse_material_spec(nodes: Any, links: Any, settings: Optional[Dict[str, Any]] = None) -> MaterialSpec:
    if not isinstance(nodes, (list, tuple)) or not nodes:
        raise ValueError("nodes must be a non-empty list of node dicts")
    if len(nodes) > MAX_NODES:
        raise ValueError(f"too many nodes (max {MAX_NODES})")
    links = links or []
    if not isinstance(links, (list, tuple)) or len(links) > MAX_LINKS:
        raise ValueError(f"links must be a list (max {MAX_LINKS})")

    parsed: List[NodeSpec] = []
    seen: Dict[str, NodeSpec] = {}
    for index, raw in enumerate(nodes):
        where = f"nodes[{index}]"
        if not isinstance(raw, dict):
            raise ValueError(f"{where} must be an object")
        node_id = str(raw.get("id", "")).strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,31}", node_id):
            raise ValueError(f"{where}: 'id' must be a short name like 'noise1' (letters, digits, _)")
        if node_id in seen:
            raise ValueError(f"{where}: duplicate id '{node_id}'")
        short, idname = _short_type(raw.get("type", ""))
        node = NodeSpec(node_id, short, idname)
        for key, value in (raw.get("inputs") or {}).items():
            node.inputs[str(key)] = _coerce_value(value, f"{where}({node_id}).inputs['{key}']")
        for key, value in (raw.get("props") or {}).items():
            if key not in ALLOWED_PROPS:
                raise ValueError(f"{where}({node_id}): property '{key}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_PROPS))}")
            if not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"{where}({node_id}).props['{key}'] must be a simple value")
            node.props[key] = value
        if raw.get("ramp") is not None:
            if short != "ValToRGB":
                raise ValueError(f"{where}({node_id}): 'ramp' only belongs on a ValToRGB node")
            ramp = raw["ramp"]
            if not isinstance(ramp, (list, tuple)) or len(ramp) < 2 or len(ramp) > 16:
                raise ValueError(f"{where}({node_id}): ramp needs 2-16 stops like [[0.3, [0,0,0,1]], [0.75, [1,1,1,1]]]")
            stops = []
            for stop in ramp:
                if not isinstance(stop, (list, tuple)) or len(stop) != 2:
                    raise ValueError(f"{where}({node_id}): each ramp stop is [position, [r, g, b, a]]")
                position = float(stop[0])
                colour = _coerce_value(stop[1], f"{where}({node_id}).ramp")
                if not isinstance(colour, list) or len(colour) not in (3, 4):
                    raise ValueError(f"{where}({node_id}): ramp colour needs 3 or 4 numbers")
                stops.append((min(1.0, max(0.0, position)), (colour + [1.0])[:4] if len(colour) == 3 else colour))
            node.ramp = sorted(stops, key=lambda s: s[0])
        if raw.get("image") is not None:
            if short != "TexImage":
                raise ValueError(f"{where}({node_id}): 'image' only belongs on a TexImage node")
            node.image = str(raw["image"])
            node.colorspace = str(raw.get("colorspace", "sRGB"))
            if node.colorspace not in ("sRGB", "Non-Color", "Linear Rec.709", "Linear"):
                raise ValueError(f"{where}({node_id}): colorspace must be sRGB or Non-Color")
        loc = raw.get("location")
        if loc is not None:
            if not isinstance(loc, (list, tuple)) or len(loc) != 2:
                raise ValueError(f"{where}({node_id}): location must be [x, y]")
            node.location = (float(loc[0]), float(loc[1]))
        parsed.append(node)
        seen[node_id] = node

    outputs = [n for n in parsed if n.type == "OutputMaterial"]
    if len(outputs) != 1:
        raise ValueError("exactly one OutputMaterial node is required")

    parsed_links: List[Tuple[str, str, str, str]] = []
    for index, link in enumerate(links):
        where = f"links[{index}]"
        if not isinstance(link, (list, tuple)) or len(link) != 2:
            raise ValueError(f"{where} must be [\"from_id.Output\", \"to_id.Input\"]")
        from_id, from_socket = _split_socket(link[0], where)
        to_id, to_socket = _split_socket(link[1], where)
        for node_id, socket, is_input in ((from_id, from_socket, False), (to_id, to_socket, True)):
            if node_id not in seen:
                raise ValueError(f"{where}: unknown node id '{node_id}'")
            table = SOCKETS.get(seen[node_id].type)
            known = table[0 if is_input else 1] if table else None
            if known is not None and not socket.isdigit() and socket not in known:
                kind = "input" if is_input else "output"
                raise ValueError(f"{where}: {seen[node_id].type} '{node_id}' has no {kind} socket '{socket}'. {kind.capitalize()}s: {', '.join(known) or '(none)'}")
        parsed_links.append((from_id, from_socket, to_id, to_socket))

    for node in parsed:                                   # inputs ke naam bhi jaanch lo (jahan table maujood hai)
        table = SOCKETS.get(node.type)
        if table:
            for name in node.inputs:
                if not name.isdigit() and name not in table[0]:
                    raise ValueError(f"{node.type} '{node.id}' has no input '{name}'. Inputs: {', '.join(table[0])}")

    clean_settings: Dict[str, Any] = {}
    for key, value in (settings or {}).items():
        if key not in ALLOWED_SETTINGS:
            raise ValueError(f"setting '{key}' is not allowed. Allowed: {', '.join(sorted(ALLOWED_SETTINGS))}")
        if value not in ALLOWED_SETTINGS[key]:
            raise ValueError(f"setting '{key}' must be one of {list(ALLOWED_SETTINGS[key])}")
        clean_settings[key] = value
    return MaterialSpec(parsed, parsed_links, clean_settings)


# =============================================================================
# Recipes
# =============================================================================
def _n(node_id, type_, **kw):
    spec = {"id": node_id, "type": type_}
    spec.update(kw)
    return spec


def _p(params: Dict[str, Any], key: str, default: Any) -> Any:
    value = params.get(key)
    return default if value is None else value


def recipe_fire_flame(p):
    """Aag: noise se toota hua emission, neeche se upar fade (Generated Z)."""
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"),
        _n("map", "Mapping", inputs={"Scale": [1.0, 1.0, float(_p(p, "stretch", 0.6))]}),
        _n("noise", "TexNoise", props={"noise_dimensions": "3D"}, inputs={"Scale": float(_p(p, "scale", 2.4)), "Detail": float(_p(p, "detail", 4.0)),
                                                                          "Roughness": 0.7, "Distortion": float(_p(p, "distortion", 0.4))}),
        _n("ramp", "ValToRGB", ramp=[[float(_p(p, "cutoff_low", 0.30)), [0, 0, 0, 1]], [float(_p(p, "cutoff_high", 0.75)), [1, 1, 1, 1]]]),
        _n("sep", "SeparateXYZ"), _n("fall", "Math", props={"operation": "SUBTRACT"}, inputs={"0": 1.0}),
        _n("shape", "Math", props={"operation": "MULTIPLY"}), _n("clip", "Math", props={"operation": "MULTIPLY", "use_clamp": True}, inputs={"1": 1.6}),
        _n("transp", "Transparent"),
        _n("em", "Emission", inputs={"Color": _p(p, "color", [1.0, 0.12, 0.005, 1.0]), "Strength": float(_p(p, "strength", 8.0))}),
        _n("mix", "MixShader")],
        "links": [["tc.Generated", "map.Vector"], ["map.Vector", "noise.Vector"], ["noise.Fac", "ramp.Fac"], ["tc.Generated", "sep.Vector"],
                  ["sep.Z", "fall.1"], ["ramp.Color", "shape.0"], ["fall.Value", "shape.1"], ["shape.Value", "clip.0"], ["clip.Value", "mix.Fac"],
                  ["transp.BSDF", "mix.1"], ["em.Emission", "mix.2"], ["mix.Shader", "out.Surface"]],
        "settings": {"surface_render_method": "DITHERED", "use_backface_culling": False}}


def recipe_ember(p):
    """Damakte angaare: kala base + noise se badalti emission."""
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"),
        _n("noise", "TexNoise", props={"noise_dimensions": "3D"}, inputs={"Scale": float(_p(p, "scale", 9.0)), "Detail": 3.0, "Roughness": 0.6}),
        _n("ramp", "ValToRGB", ramp=[[0.35, [0.02, 0.0, 0.0, 1]], [0.7, _p(p, "color", [1.0, 0.12, 0.005, 1.0])]]),
        _n("scale", "Math", props={"operation": "MULTIPLY"}, inputs={"1": float(_p(p, "strength", 10.0))}),
        _n("bsdf", "Principled", inputs={"Base Color": [0.03, 0.01, 0.005, 1.0], "Roughness": 0.55})],
        "links": [["tc.Object", "noise.Vector"], ["noise.Fac", "ramp.Fac"], ["noise.Fac", "scale.0"], ["ramp.Color", "bsdf.Emission Color"],
                  ["scale.Value", "bsdf.Emission Strength"], ["bsdf.BSDF", "out.Surface"]]}


def recipe_smoke_volume(p):
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"), _n("map", "Mapping"),
        _n("noise", "TexNoise", props={"noise_dimensions": "3D"}, inputs={"Scale": float(_p(p, "scale", 1.2)), "Detail": 5.0, "Roughness": 0.75}),
        _n("dens", "Math", props={"operation": "MULTIPLY"}, inputs={"1": float(_p(p, "density", 0.19))}),
        _n("vol", "VolumePrincipled", inputs={"Color": _p(p, "color", [0.05, 0.045, 0.04, 1.0])})],
        "links": [["tc.Generated", "map.Vector"], ["map.Vector", "noise.Vector"], ["noise.Fac", "dens.0"], ["dens.Value", "vol.Density"],
                  ["vol.Volume", "out.Volume"]]}


def _bumped_principled(p, color_ramp, noise_scale, bump, roughness, extra_inputs=None, noise_detail=8.0):
    inputs = {"Roughness": roughness}
    inputs.update(extra_inputs or {})
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"),
        _n("noise", "TexNoise", props={"noise_dimensions": "3D"}, inputs={"Scale": noise_scale, "Detail": noise_detail, "Roughness": 0.65}),
        _n("ramp", "ValToRGB", ramp=color_ramp), _n("bump", "Bump", inputs={"Strength": bump, "Distance": 0.02}),
        _n("bsdf", "Principled", inputs=inputs)],
        "links": [["tc.Object", "noise.Vector"], ["noise.Fac", "ramp.Fac"], ["ramp.Color", "bsdf.Base Color"], ["noise.Fac", "bump.Height"],
                  ["bump.Normal", "bsdf.Normal"], ["bsdf.BSDF", "out.Surface"]]}


def recipe_charred_wood(p):
    base = _p(p, "color", [0.02, 0.012, 0.008, 1.0])
    return _bumped_principled(p, [[0.3, [0.004, 0.003, 0.002, 1]], [0.7, base]], 14.0, 0.8, 0.95)


def recipe_wood_grain(p):
    dark, light = _p(p, "dark", [0.18, 0.09, 0.04, 1.0]), _p(p, "light", [0.45, 0.26, 0.12, 1.0])
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"), _n("map", "Mapping", inputs={"Scale": [1.0, 1.0, 0.08]}),
        _n("wave", "TexWave", props={"wave_type": "BANDS", "bands_direction": "X"},
           inputs={"Scale": float(_p(p, "scale", 3.0)), "Distortion": 7.0, "Detail": 3.0, "Detail Scale": 2.0, "Detail Roughness": 0.6}),
        _n("ramp", "ValToRGB", ramp=[[0.2, dark], [0.8, light]]), _n("bump", "Bump", inputs={"Strength": 0.25, "Distance": 0.01}),
        _n("bsdf", "Principled", inputs={"Roughness": float(_p(p, "roughness", 0.55))})],
        "links": [["tc.Object", "map.Vector"], ["map.Vector", "wave.Vector"], ["wave.Fac", "ramp.Fac"], ["ramp.Color", "bsdf.Base Color"],
                  ["wave.Fac", "bump.Height"], ["bump.Normal", "bsdf.Normal"], ["bsdf.BSDF", "out.Surface"]]}


def recipe_rough_stone(p):
    base = _p(p, "color", [0.32, 0.29, 0.26, 1.0])
    dark = [c * 0.45 for c in base[:3]] + [1.0]
    return _bumped_principled(p, [[0.25, dark], [0.75, base]], float(_p(p, "scale", 5.0)), 1.2, 0.85)


def recipe_dirt_ground(p):
    base = _p(p, "color", [0.07, 0.05, 0.035, 1.0])
    dark = [c * 0.4 for c in base[:3]] + [1.0]
    return _bumped_principled(p, [[0.2, dark], [0.8, base]], float(_p(p, "scale", 3.0)), 0.9, 0.95, noise_detail=10.0)


def recipe_glass(p):
    return {"nodes": [_n("out", "OutputMaterial"), _n("bsdf", "Principled", inputs={
        "Base Color": _p(p, "color", [1.0, 1.0, 1.0, 1.0]), "Roughness": float(_p(p, "roughness", 0.02)), "IOR": float(_p(p, "ior", 1.45)),
        "Transmission Weight": 1.0})],
        "links": [["bsdf.BSDF", "out.Surface"]], "settings": {"surface_render_method": "DITHERED"}}


def recipe_car_paint(p):
    return {"nodes": [_n("out", "OutputMaterial"), _n("bsdf", "Principled", inputs={
        "Base Color": _p(p, "color", [0.55, 0.02, 0.02, 1.0]), "Metallic": float(_p(p, "metallic", 0.65)), "Roughness": float(_p(p, "roughness", 0.32)),
        "Coat Weight": 1.0, "Coat Roughness": 0.03})], "links": [["bsdf.BSDF", "out.Surface"]]}


def recipe_metal_brushed(p):
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"), _n("map", "Mapping", inputs={"Scale": [1.0, 60.0, 1.0]}),
        _n("noise", "TexNoise", inputs={"Scale": 40.0, "Detail": 6.0, "Roughness": 0.7}), _n("bump", "Bump", inputs={"Strength": 0.08, "Distance": 0.002}),
        _n("bsdf", "Principled", inputs={"Base Color": _p(p, "color", [0.72, 0.72, 0.75, 1.0]), "Metallic": 1.0,
                                         "Roughness": float(_p(p, "roughness", 0.35))})],
        "links": [["tc.Object", "map.Vector"], ["map.Vector", "noise.Vector"], ["noise.Fac", "bump.Height"], ["bump.Normal", "bsdf.Normal"],
                  ["bsdf.BSDF", "out.Surface"]]}


def recipe_rubber(p):
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"), _n("noise", "TexNoise", inputs={"Scale": 120.0, "Detail": 3.0}),
        _n("bump", "Bump", inputs={"Strength": 0.15, "Distance": 0.002}),
        _n("bsdf", "Principled", inputs={"Base Color": _p(p, "color", [0.02, 0.02, 0.022, 1.0]), "Roughness": 0.85})],
        "links": [["tc.Object", "noise.Vector"], ["noise.Fac", "bump.Height"], ["bump.Normal", "bsdf.Normal"], ["bsdf.BSDF", "out.Surface"]]}


def recipe_water(p):
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"), _n("noise", "TexNoise", props={"noise_dimensions": "3D"}, inputs={"Scale": 4.0, "Detail": 6.0}),
        _n("bump", "Bump", inputs={"Strength": 0.12, "Distance": 0.05}),
        _n("bsdf", "Principled", inputs={"Base Color": _p(p, "color", [0.35, 0.55, 0.65, 1.0]), "Roughness": 0.03, "IOR": 1.33, "Transmission Weight": 1.0})],
        "links": [["tc.Object", "noise.Vector"], ["noise.Fac", "bump.Height"], ["bump.Normal", "bsdf.Normal"], ["bsdf.BSDF", "out.Surface"]],
        "settings": {"surface_render_method": "DITHERED"}}


def recipe_glow(p):
    """Lantern/lamp/screen jaisa seedha chamakta saaf material."""
    return {"nodes": [_n("out", "OutputMaterial"), _n("em", "Emission", inputs={
        "Color": _p(p, "color", [1.0, 0.65, 0.25, 1.0]), "Strength": float(_p(p, "strength", 12.0))})], "links": [["em.Emission", "out.Surface"]]}


def recipe_fabric(p):
    return {"nodes": [
        _n("out", "OutputMaterial"), _n("tc", "TexCoord"), _n("brick", "TexChecker", inputs={"Scale": 90.0}),
        _n("bump", "Bump", inputs={"Strength": 0.12, "Distance": 0.002}),
        _n("bsdf", "Principled", inputs={"Base Color": _p(p, "color", [0.35, 0.25, 0.2, 1.0]), "Roughness": 0.9, "Sheen Weight": 0.6, "Sheen Roughness": 0.5})],
        "links": [["tc.Object", "brick.Vector"], ["brick.Fac", "bump.Height"], ["bump.Normal", "bsdf.Normal"], ["bsdf.BSDF", "out.Surface"]]}


RECIPES: Dict[str, Tuple[Callable[[Dict[str, Any]], Dict[str, Any]], str]] = {
    "fire_flame": (recipe_fire_flame, "aag/mashaal ki lau (color, strength, scale, detail, stretch, distortion). Flame mesh par lagao; kuch bhi 'Transparent' ke saath"),
    "ember": (recipe_ember, "damakte angaare/coal (color, strength, scale)"), "smoke_volume": (recipe_smoke_volume, "dhuan/dhundh VOLUME (density, color, scale) - cube par"),
    "charred_wood": (recipe_charred_wood, "jali lakdi (color)"), "wood_grain": (recipe_wood_grain, "lakdi ke daane (dark, light, scale, roughness)"),
    "rough_stone": (recipe_rough_stone, "khurdura patthar (color, scale)"), "dirt_ground": (recipe_dirt_ground, "mitti/zameen (color, scale)"),
    "glass": (recipe_glass, "sheesha (color, roughness, ior)"), "car_paint": (recipe_car_paint, "gaadi ka paint clearcoat ke saath (color, metallic, roughness)"),
    "metal_brushed": (recipe_metal_brushed, "brushed dhaatu (color, roughness)"), "rubber": (recipe_rubber, "rabar/tyre (color)"),
    "water": (recipe_water, "paani (color)"), "glow": (recipe_glow, "seedha chamakta: lantern, lamp, screen (color, strength)"),
    "fabric": (recipe_fabric, "kapda (color)"),
}


def build_recipe(name: str, params: Optional[Dict[str, Any]] = None) -> MaterialSpec:
    key = str(name).strip().lower().replace(" ", "_").replace("-", "_")
    if key not in RECIPES:
        raise ValueError(f"unknown recipe '{name}'. Recipes: {', '.join(sorted(RECIPES))}")
    raw = RECIPES[key][0](dict(params or {}))
    return parse_material_spec(raw["nodes"], raw["links"], raw.get("settings"))


def recipe_help() -> str:
    return "; ".join(f"{k} = {v[1]}" for k, v in sorted(RECIPES.items()))


def layout(spec: MaterialSpec) -> Dict[str, Tuple[float, float]]:
    """Node editor mein sahi dikhne ke liye positions: output sabse daayein, upstream baayein, ek column mein upar-neeche."""
    depth = {n.id: 0 for n in spec.nodes}
    for _ in range(len(spec.nodes)):
        changed = False
        for from_id, _fs, to_id, _ts in spec.links:
            if depth[to_id] < depth[from_id] + 1:
                depth[to_id] = depth[from_id] + 1
                changed = True
        if not changed:
            break
    top = max(depth.values()) if depth else 0
    rows: Dict[int, int] = {}
    placed: Dict[str, Tuple[float, float]] = {}
    for node in spec.nodes:
        if node.location is not None:
            placed[node.id] = node.location
            continue
        column = depth[node.id]
        row = rows.get(column, 0)
        rows[column] = row + 1
        placed[node.id] = (float((column - top) * 280), float(-row * 240))
    return placed


def viewport_color(spec: MaterialSpec) -> Optional[List[float]]:
    """Solid viewport mein node material ka rang andaaze se dikhane ke liye: pehle Emission/Principled ka rang."""
    for key in ("Emission", "Principled"):
        for node in spec.nodes:
            if node.type == key:
                for socket in ("Color", "Base Color"):
                    value = node.inputs.get(socket)
                    if isinstance(value, list) and len(value) in (3, 4):
                        return (list(value) + [1.0])[:4]
    return None