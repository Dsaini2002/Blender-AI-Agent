"""
Input/Output Models — Step 2.2 + 2.4 + 2.5
=============================================
Hinglish: Har tool ka input ek typed dataclass hai — random dict nahi.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import json


@dataclass
class CreateObjectInput:
    """object.create tool ke liye input contract."""
    name: str
    object_type: str = "MESH"
    primitive: str = "CUBE"
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    # Hinglish: Chhote/fast models (jaise openai/gpt-oss-20b) kabhi-kabhi
    # do-parameter schema confuse kar dete hain aur primitive naam
    # (CUBE, SPHERE, etc.) galti se `object_type` field mein bhej dete
    # hain, jabki `object_type` sirf "MESH" jaisi generic value expect
    # karta hai. Isse "Unsupported object_type: CUBE" jaisi crash aati
    # thi. Yahan defensively normalize karte hain: agar object_type mein
    # koi known primitive naam aaye, usse primitive field mein shift
    # kar dete hain aur object_type ko wapas "MESH" set kar dete hain —
    # bina koi error diye, jaisa bada model (120b) khud karta hai.
    # Hinglish: Sirf MESH-unique naam (CIRCLE/CUBE jaise naam CURVE/EMPTY
    # mein bhi hain, isliye unhe yahan normalize nahi karte - ambiguous hai).
    _KNOWN_PRIMITIVES = {
        "CUBE", "SPHERE", "ICOSPHERE", "CONE", "CYLINDER", "PLANE", "TORUS", "GRID", "MONKEY",
    }
    # object_type ke liye valid values - CreateObjectTool in sab categories
    # mein se object bana sakta hai (har ek ke apne primitive names hain,
    # dekho bridge/blender_bridge.py ki _CREATE_OPS).
    KNOWN_OBJECT_TYPES = {
        "MESH", "CURVE", "SURFACE", "METABALL", "EMPTY", "LIGHT", "ARMATURE", "LATTICE",
    }

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CreateObjectInput.name must be a non-empty string")

        if isinstance(self.object_type, str) and self.object_type.upper() in self._KNOWN_PRIMITIVES:
            self.primitive = self.object_type.upper()
            self.object_type = "MESH"

        self.location = _vec3(self.location, "CreateObjectInput.location")


@dataclass
class DeleteObjectInput:
    """object.delete tool ke liye input contract."""
    name: str

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("DeleteObjectInput.name must be a non-empty string")

@dataclass
class RecalculateNormalsInput:
    """geometry.recalculate_normals tool ke liye input contract."""
    object_name: str

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("RecalculateNormalsInput.object_name must be a non-empty string")


@dataclass
class SeparateOverlapInput:
    """geometry.separate_overlap tool ke liye input contract."""
    object_name: str
    offset: List[float] = field(default_factory=lambda: [2.0, 0.0, 0.0])

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("SeparateOverlapInput.object_name must be a non-empty string")
        if len(self.offset) != 3:
            raise ValueError("SeparateOverlapInput.offset must have exactly 3 values [x, y, z]")
        
@dataclass
class DuplicateObjectInput:
    """object.duplicate tool ke liye input contract."""
    name: str
    new_name: str = ""

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("DuplicateObjectInput.name must be a non-empty string")


@dataclass
class RenameObjectInput:
    """object.rename tool ke liye input contract."""
    old_name: str
    new_name: str

    def __post_init__(self):
        if not self.old_name or not isinstance(self.old_name, str):
            raise ValueError("RenameObjectInput.old_name must be a non-empty string")
        if not self.new_name or not isinstance(self.new_name, str):
            raise ValueError("RenameObjectInput.new_name must be a non-empty string")


@dataclass
class TransformObjectInput:
    """object.transform tool ke liye input contract."""
    name: str
    location: Optional[List[float]] = None
    rotation: Optional[List[float]] = None
    scale: Optional[List[float]] = None

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("TransformObjectInput.name must be a non-empty string")

        # Hinglish: Gemini kabhi "1, 2, 3" string, {"x":..,"y":..,"z":..} dict ya proto list bhejta hai —
        # pehle ye sab "must have exactly 3 values" par fail hote the. Ab _vec3 inhe [x, y, z] banata hai,
        # aur galat value par error mein asli value dikhata hai.
        for field_name in ("location", "rotation", "scale"):
            value = getattr(self, field_name)
            if value is not None:
                setattr(self, field_name, _vec3(value, f"TransformObjectInput.{field_name}"))

        if self.location is None and self.rotation is None and self.scale is None:
            raise ValueError("TransformObjectInput requires at least one of: location, rotation, scale")


@dataclass
class CreateMaterialInput:
    """material.create tool ke liye input contract."""
    name: str
    color: Optional[List[float]] = None

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CreateMaterialInput.name must be a non-empty string")
        if self.color is not None:
            # Hinglish: Gemini kabhi ["0.8","0.2","0.2"] (strings), "red", "#FF0000" ya {"r":..} bhejta hai —
            # pehle ye seedha Blender tak jaata tha: "expected sequence items of type float, not str".
            self.color = _coerce_color(self.color, "CreateMaterialInput.color")
            if len(self.color) not in (3, 4):
                raise ValueError("CreateMaterialInput.color must have 3 (RGB) or 4 (RGBA) values")


@dataclass
class AssignMaterialInput:
    """material.assign tool ke liye input contract."""
    object_name: str
    material_name: str

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("AssignMaterialInput.object_name must be a non-empty string")
        if not self.material_name or not isinstance(self.material_name, str):
            raise ValueError("AssignMaterialInput.material_name must be a non-empty string")


@dataclass
class ModifyMaterialInput:
    """material.modify tool ke liye input contract."""
    name: str
    color: Optional[List[float]] = None
    roughness: Optional[float] = None
    metallic: Optional[float] = None
    emission_color: Optional[List[float]] = None
    emission_strength: Optional[float] = None

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("ModifyMaterialInput.name must be a non-empty string")
        if self.emission_color is not None:
            self.emission_color = _coerce_color(self.emission_color, "ModifyMaterialInput.emission_color")
            if len(self.emission_color) not in (3, 4):
                raise ValueError("ModifyMaterialInput.emission_color must have 3 (RGB) or 4 (RGBA) values")
        if self.emission_strength is not None:
            self.emission_strength = _coerce_number(self.emission_strength, "ModifyMaterialInput.emission_strength")
            if not (0.0 <= self.emission_strength <= 1000.0):
                raise ValueError("ModifyMaterialInput.emission_strength must be between 0.0 and 1000.0")
        # Hinglish: sirf emission_color dene par strength default 0 hoti hai
        # (Blender 4.x), matlab glow dikhega hi nahi — isliye sensible default.
        if self.emission_color is not None and self.emission_strength is None:
            self.emission_strength = 1.0
        if self.color is not None:
            self.color = _coerce_color(self.color, "ModifyMaterialInput.color")
            if len(self.color) not in (3, 4):
                raise ValueError("ModifyMaterialInput.color must have 3 (RGB) or 4 (RGBA) values")
        if self.roughness is not None:
            self.roughness = _coerce_number(self.roughness, "ModifyMaterialInput.roughness")
            if not (0.0 <= self.roughness <= 1.0):
                raise ValueError("ModifyMaterialInput.roughness must be between 0.0 and 1.0")
        if self.metallic is not None:
            self.metallic = _coerce_number(self.metallic, "ModifyMaterialInput.metallic")
            if not (0.0 <= self.metallic <= 1.0):
                raise ValueError("ModifyMaterialInput.metallic must be between 0.0 and 1.0")
        if (self.color is None and self.roughness is None and self.metallic is None
                and self.emission_color is None and self.emission_strength is None):
            raise ValueError(
                "ModifyMaterialInput requires at least one of: color, roughness, metallic, "
                "emission_color, emission_strength"
            )
@dataclass
class AddModifierInput:
    """modifier.add tool ke liye input contract."""
    object_name: str
    modifier_name: str
    modifier_type: str = "BEVEL"

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("AddModifierInput.object_name must be a non-empty string")
        if not self.modifier_name or not isinstance(self.modifier_name, str):
            raise ValueError("AddModifierInput.modifier_name must be a non-empty string")


@dataclass
class RemoveModifierInput:
    """modifier.remove tool ke liye input contract."""
    object_name: str
    modifier_name: str

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("RemoveModifierInput.object_name must be a non-empty string")
        if not self.modifier_name or not isinstance(self.modifier_name, str):
            raise ValueError("RemoveModifierInput.modifier_name must be a non-empty string")


@dataclass
class ConfigureModifierInput:
    """modifier.configure tool ke liye input contract."""
    object_name: str
    modifier_name: str
    properties: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("ConfigureModifierInput.object_name must be a non-empty string")
        if not self.modifier_name or not isinstance(self.modifier_name, str):
            raise ValueError("ConfigureModifierInput.modifier_name must be a non-empty string")

        # Hinglish: Gemini kabhi-kabhi `properties` ko dict ki jagah JSON
        # STRING bhej deta hai (e.g. '{"width": 0.03}'), jisse pehle
        # `.items()` par AttributeError crash hoti thi. Yahan defensively
        # parse karte hain - jaise CreateObjectInput mein object_type/
        # primitive ka defensive-fix hai.
        if isinstance(self.properties, str):
            try:
                parsed = json.loads(self.properties)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"ConfigureModifierInput.properties must be a dict, got an "
                    f"unparseable string: {self.properties!r}"
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"ConfigureModifierInput.properties must be a dict, got JSON {type(parsed).__name__}"
                )
            self.properties = parsed

        if not isinstance(self.properties, dict):
            raise ValueError(
                f"ConfigureModifierInput.properties must be a dict, got {type(self.properties).__name__}"
            )

        if not self.properties:
            raise ValueError("ConfigureModifierInput.properties must not be empty")
@dataclass
class ImportModelInput:
    """asset.import_model tool ke liye input contract - koi LOCAL file
    (.obj/.fbx/.glb/.gltf) jo user ne pehle se disk par rakha hai."""
    filepath: str
    name: Optional[str] = None
    scale: Optional[List[float]] = None

    SUPPORTED_EXTENSIONS = (".obj", ".fbx", ".glb", ".gltf")

    def __post_init__(self):
        if not self.filepath or not isinstance(self.filepath, str):
            raise ValueError("ImportModelInput.filepath must be a non-empty string")
        ext = self.filepath.lower().rsplit(".", 1)
        ext = f".{ext[1]}" if len(ext) == 2 else ""
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"ImportModelInput.filepath must end with one of "
                f"{self.SUPPORTED_EXTENSIONS}, got: {self.filepath!r}"
            )
        if self.scale is not None and len(self.scale) != 3:
            raise ValueError("ImportModelInput.scale must have exactly 3 values [x, y, z]")


@dataclass
class BuildTemplateInput:
    """template.build tool ke liye input contract - ek poore pre-defined
    body structure (jaise 'humanoid') ko ek exact, fixed spec se banata
    hai. Coordinates guess nahi hote - templates/<name>.json se aate hain."""
    template_name: str
    prefix: str = ""
    colors: Optional[dict] = None
    include_optional_parts: bool = True

    def __post_init__(self):
        if not self.template_name or not isinstance(self.template_name, str):
            raise ValueError("BuildTemplateInput.template_name must be a non-empty string")
        if not isinstance(self.prefix, str):
            raise ValueError("BuildTemplateInput.prefix must be a string")

        # Hinglish: Gemini kabhi-kabhi `colors` ko dict ki jagah JSON
        # STRING bhej deta hai (jaisa ConfigureModifierInput.properties
        # mein hota tha) - defensively parse karte hain, crash nahi.
        if isinstance(self.colors, str):
            try:
                parsed = json.loads(self.colors)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"BuildTemplateInput.colors must be a dict, got an unparseable "
                    f"string: {self.colors!r}"
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"BuildTemplateInput.colors must be a dict, got JSON {type(parsed).__name__}"
                )
            self.colors = parsed

        if self.colors is not None and not isinstance(self.colors, dict):
            raise ValueError(
                f"BuildTemplateInput.colors must be a dict of "
                f"{{material_group: [r,g,b,a]}}, got {type(self.colors).__name__}"
            )


@dataclass
class ListBlendObjectsInput:
    """asset.list_blend_objects tool ke liye input - .blend file ke andar
    kaun se objects hain, ye dekhne ke liye (import karne se pehle)."""
    filepath: str

    def __post_init__(self):
        if not self.filepath or not isinstance(self.filepath, str):
            raise ValueError("ListBlendObjectsInput.filepath must be a non-empty string")
        if not self.filepath.lower().endswith(".blend"):
            raise ValueError("ListBlendObjectsInput.filepath must end with .blend")


@dataclass
class ImportBlendInput:
    """asset.import_blend tool ke liye input - .blend file se specific
    (ya sab) objects scene mein laata hai."""
    filepath: str
    object_names: Optional[List[str]] = None
    name_prefix: Optional[str] = None

    def __post_init__(self):
        if not self.filepath or not isinstance(self.filepath, str):
            raise ValueError("ImportBlendInput.filepath must be a non-empty string")
        if not self.filepath.lower().endswith(".blend"):
            raise ValueError("ImportBlendInput.filepath must end with .blend")
        if self.object_names is not None and not isinstance(self.object_names, list):
            raise ValueError("ImportBlendInput.object_names must be a list of strings or omitted")


@dataclass
class CreateCameraInput:
    """camera.create tool ke liye input contract."""
    name: str
    location: Optional[List[float]] = None
    rotation: Optional[List[float]] = None

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CreateCameraInput.name must be a non-empty string")
        if self.location is not None:
            self.location = _vec3(self.location, "CreateCameraInput.location")
        if self.rotation is not None:
            self.rotation = _vec3(self.rotation, "CreateCameraInput.rotation")


@dataclass
class SetCameraInput:
    """camera.set tool ke liye input contract."""
    name: str

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("SetCameraInput.name must be a non-empty string")


@dataclass
class RenderPreviewInput:
    """
    render.preview tool ke liye input contract.

    filepath : image ka naam (folder ignore ho sakta hai — dekho image_paths.resolve_image_path)
    draft    : True = tez, chhota 640x360 preview (vision check ke liye kaafi)
    width/height : pixels (16-8192). Sirf ek diya to doosra 16:9 se nikalta hai.
    """
    filepath: str
    width: Optional[int] = None
    height: Optional[int] = None
    draft: bool = False

    def __post_init__(self):
        if not self.filepath or not isinstance(self.filepath, str) or not self.filepath.strip():
            raise ValueError("RenderPreviewInput.filepath must be a non-empty string")

        self.draft = _coerce_bool(self.draft, "RenderPreviewInput.draft")
        for field_name in ("width", "height"):
            value = getattr(self, field_name)
            if value is not None:
                value = _coerce_number(value, f"RenderPreviewInput.{field_name}", integer=True)
                if not (16 <= value <= 8192):
                    raise ValueError(f"RenderPreviewInput.{field_name} must be between 16 and 8192 pixels")
                setattr(self, field_name, value)

    def resolution(self):
        """(width, height) jab size maanga gaya ho, warna None (scene ki apni resolution rehti hai)."""
        if self.width is not None and self.height is not None:
            return (self.width, self.height)
        if self.width is not None:
            return (self.width, max(16, round(self.width * 9 / 16)))
        if self.height is not None:
            return (max(16, round(self.height * 16 / 9)), self.height)
        if self.draft:
            return (640, 360)
        return None


# ---------------------------------------------------------
# Plain-Python normalisation (Gemini SDK ke proto containers ke liye)
# ---------------------------------------------------------
def to_plain(value):
    """
    Hinglish: Gemini ka `fc.args` shallow dict(...) se aata hai, to uske andar ki lists/dicts
    proto-plus ke `RepeatedComposite` / `MapComposite` objects hote hain. Ye print mein bilkul
    [1.0, 0.4, 0.0] jaise dikhte hain, lekin `isinstance(x, list)` False deta hai — isi se
    "must be a list of numbers" jaise confusing errors aaye. Ye function unhe recursively asli
    Python list/dict/str/number mein badal deta hai. Plain data par koi asar nahi.
    """
    if value is None or isinstance(value, (str, bytes, bool, int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if hasattr(value, "items") and callable(value.items):          # MapComposite & dict-jaise
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    if hasattr(value, "__iter__"):                                  # RepeatedComposite & list-jaise
        return [to_plain(v) for v in value]
    return value

# ---------------------------------------------------------
# Lenient number coercion (LLMs often send 500.0 or "500" instead of 500)
# ---------------------------------------------------------
def _coerce_number(value, label, *, integer=False):
    """
    Hinglish: Chhote LLMs `500` ki jagah `500.0` ya `"500"` bhej dete hain.
    Pehle ye poore task ko fail kar deta tha. Ab hum safe conversions karte hain:
    numeric string -> number, integral float -> int (jab integer chahiye).
    Bool aur jo cheez number nahi ban sakti, wo abhi bhi ValueError hai.
    """
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a number, not a boolean")
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError:
            raise ValueError(f"{label} must be a number, got '{value}'") from None
    if not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number, got {type(value).__name__}")
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{label} must be a finite number")
    if integer:
        if float(value) != int(value):
            raise ValueError(f"{label} must be a whole number, got {value}")
        return int(value)
    return float(value) if not isinstance(value, int) else value


def _coerce_bool(value, label):
    """true/false, "true"/"false", 1/0 -> bool."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false", "yes", "no", "1", "0"):
        return value.strip().lower() in ("true", "yes", "1")
    if value in (0, 1):
        return bool(value)
    raise ValueError(f"{label} must be true or false")


def _coerce_list(value, label):
    """[1,2,3] ya "1, 2, 3" ya "[1,2,3]" -> list of floats."""
    value = to_plain(value)
    if isinstance(value, dict):
        # Hinglish: {"x": 0, "y": 0, "z": 3} (case-insensitive) -> [0, 0, 3]
        lowered = {str(k).lower(): v for k, v in value.items()}
        if all(axis in lowered for axis in ("x", "y", "z")):
            value = [lowered["x"], lowered["y"], lowered["z"]]
        else:
            raise ValueError(f"{label} dict must have x, y, z keys, e.g. {{\"x\": 0, \"y\": 0, \"z\": 3}}")
    if isinstance(value, str):
        cleaned = value.strip().strip("[]()")
        parts = [p for p in cleaned.replace(";", ",").split(",") if p.strip()]
        value = parts
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list of numbers like [x, y, z]")
    return [_coerce_number(v, label) for v in value]



_NAMED_COLORS = {
    "red": [1.0, 0.0, 0.0], "orange": [1.0, 0.5, 0.0], "yellow": [1.0, 0.9, 0.0],
    "green": [0.0, 0.8, 0.1], "blue": [0.0, 0.2, 1.0], "purple": [0.5, 0.0, 1.0],
    "pink": [1.0, 0.4, 0.7], "white": [1.0, 1.0, 1.0], "black": [0.0, 0.0, 0.0],
    "cyan": [0.0, 1.0, 1.0], "magenta": [1.0, 0.0, 1.0], "brown": [0.4, 0.2, 0.05],
    "gray": [0.5, 0.5, 0.5], "grey": [0.5, 0.5, 0.5], "gold": [1.0, 0.7, 0.1],
    "amber": [1.0, 0.55, 0.0], "violet": [0.55, 0.2, 0.9], "teal": [0.0, 0.5, 0.5],
}

_NUMBER_PATTERN = r"-?\d+(?:\.\d+)?(?:e-?\d+)?|-?\.\d+"


def _parse_color(value, label):
    """Hinglish: Ek colour ko [r, g, b(, a)] numbers mein badalta hai — andar ka kaam, errors upar wrap hote hain."""
    import re

    value = to_plain(value)

    # [[1, 0.5, 0]] ya ["orange"] jaisa ek-element wala wrapper
    if isinstance(value, (list, tuple)) and len(value) == 1 and isinstance(value[0], (list, tuple, dict, str)):
        return _parse_color(value[0], label)

    if isinstance(value, dict):
        lowered = {str(k).lower(): v for k, v in value.items()}
        for keys in (("r", "g", "b", "a"), ("red", "green", "blue", "alpha")):
            if all(k in lowered for k in keys[:3]):
                channels = [lowered[k] for k in keys[:3]]
                if keys[3] in lowered:
                    channels.append(lowered[keys[3]])
                return [_coerce_number(c, label) for c in channels]
        for key in ("hex", "color", "colour", "rgb", "rgba", "value", "code"):
            if key in lowered:
                return _parse_color(lowered[key], label)
        raise ValueError("unsupported colour dict")

    if isinstance(value, str):
        text = value.strip().lower()
        if text in _NAMED_COLORS:
            return list(_NAMED_COLORS[text])

        # "#FF8000", "#f80", "ff8000", "#FF8000FF"
        hex_digits = text.lstrip("#")
        if hex_digits and all(c in "0123456789abcdef" for c in hex_digits):
            if len(hex_digits) == 3 and text.startswith("#"):
                hex_digits = "".join(c * 2 for c in hex_digits)
            if len(hex_digits) in (6, 8) and (text.startswith("#") or len(hex_digits) == 6):
                return [int(hex_digits[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]

        # "rgb(255, 128, 0)", "(1, 0.5, 0)", "1.0 0.5 0.0", "R:1 G:0.5 B:0"
        numbers = re.findall(_NUMBER_PATTERN, text)
        if len(numbers) in (3, 4):
            return [float(n) for n in numbers]

        # "bright orange", "glowing orange light" (sirf tab jab koi number nahi)
        if not numbers:
            for word in re.findall(r"[a-z]+", text):
                if word in _NAMED_COLORS:
                    return list(_NAMED_COLORS[word])
        raise ValueError("unrecognised colour string")

    if isinstance(value, (list, tuple)):
        return [_coerce_number(v, label) for v in value]

    raise ValueError("unsupported colour type")


def _coerce_color(value, label):
    """
    Hinglish: LLM colour kai tarah se bhejte hain — [1,0.5,0], "1 0.5 0", {"r":1,"g":0.5,"b":0},
    "#FF8000", "rgb(255,128,0)", "orange", "bright orange", [255,128,0]... sab ko [r, g, b(, a)]
    (0-1 scale) mein badalta hai. Na samajh aaye to error mein asli value dikhata hai, taaki
    pata chale LLM ne kya bheja.
    """
    try:
        channels = _parse_color(value, label)
    except ValueError:
        shown = repr(to_plain(value))
        if len(shown) > 80:
            shown = shown[:80] + "..."
        raise ValueError(
            f"{label} must be [r, g, b] numbers (0-1), a hex like '#FF8000', or a colour name "
            f"like 'orange' (got {shown})"
        ) from None

    # 0-255 scale ([255, 128, 0]) -> 0-1
    rgb = channels[:3]
    if rgb and max(rgb) >= 10 and max(rgb) <= 255 and all(c >= 0 and float(c).is_integer() for c in rgb):
        channels = [c / 255.0 for c in rgb] + channels[3:]
    return channels


# ---------------------------------------------------------
# Retopology
# ---------------------------------------------------------
RETOPO_METHODS = ("QUADRIFLOW", "VOXEL", "DECIMATE")


@dataclass
class AnalyzeTopologyInput:
    """retopology.analyze tool ke liye input contract."""
    object_name: str

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("AnalyzeTopologyInput.object_name must be a non-empty string")


@dataclass
class RetopologyInput:
    """
    retopology.remesh tool ke liye input contract.

    method:
      QUADRIFLOW - clean quad-dominant topology (target_faces use karta hai)
      VOXEL      - uniform even topology (voxel_size use karta hai)
      DECIMATE   - sirf poly count kam karta hai (decimate_ratio use karta hai)
    """
    object_name: str
    method: str = "QUADRIFLOW"
    target_faces: int = 2000
    voxel_size: float = 0.05
    decimate_ratio: float = 0.5
    preserve_sharp: bool = True
    smooth_normals: bool = True
    new_name: str = ""
    hide_original: bool = True

    def __post_init__(self):
        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("RetopologyInput.object_name must be a non-empty string")

        self.method = str(self.method).upper()
        if self.method not in RETOPO_METHODS:
            raise ValueError(
                f"RetopologyInput.method must be one of {list(RETOPO_METHODS)}, got '{self.method}'"
            )
        self.target_faces = _coerce_number(self.target_faces, "RetopologyInput.target_faces", integer=True)
        if not (4 <= self.target_faces <= 1_000_000):
            raise ValueError("RetopologyInput.target_faces must be an integer between 4 and 1,000,000")

        self.voxel_size = _coerce_number(self.voxel_size, "RetopologyInput.voxel_size")
        if self.voxel_size <= 0:
            raise ValueError("RetopologyInput.voxel_size must be a positive number")

        self.decimate_ratio = _coerce_number(self.decimate_ratio, "RetopologyInput.decimate_ratio")
        if not (0.0 < self.decimate_ratio < 1.0):
            raise ValueError("RetopologyInput.decimate_ratio must be between 0 and 1 (exclusive)")

        self.preserve_sharp = _coerce_bool(self.preserve_sharp, "RetopologyInput.preserve_sharp")
        self.smooth_normals = _coerce_bool(self.smooth_normals, "RetopologyInput.smooth_normals")
        self.hide_original = _coerce_bool(self.hide_original, "RetopologyInput.hide_original")

        if not self.new_name:
            self.new_name = f"{self.object_name}_retopo"


# ---------------------------------------------------------
# Lights + World
# ---------------------------------------------------------
LIGHT_TYPES = ("POINT", "SUN", "SPOT", "AREA")


def _validate_rgb(value, label):
    if len(value) not in (3, 4):
        raise ValueError(f"{label} must have 3 (RGB) or 4 (RGBA) values")
    for channel in value[:3]:
        if not isinstance(channel, (int, float)) or isinstance(channel, bool) or not (0.0 <= channel <= 1.0):
            raise ValueError(f"{label} RGB values must be numbers between 0.0 and 1.0")


@dataclass
class CreateLightInput:
    """
    light.create tool ke liye input contract.

    energy units: POINT/SPOT/AREA = Watts (e.g. 500-1000), SUN = strength (e.g. 1-5).
    """
    name: str
    light_type: str = "POINT"
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 3.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    color: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    energy: float = 1000.0
    size: float = 0.25
    spot_angle: float = 45.0

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CreateLightInput.name must be a non-empty string")

        self.light_type = str(self.light_type).upper()
        if self.light_type not in LIGHT_TYPES:
            raise ValueError(
                f"CreateLightInput.light_type must be one of {list(LIGHT_TYPES)}, got '{self.light_type}'"
            )
        self.location = _coerce_list(self.location, "CreateLightInput.location")
        self.rotation = _coerce_list(self.rotation, "CreateLightInput.rotation")
        if len(self.location) != 3:
            raise ValueError("CreateLightInput.location must have exactly 3 values [x, y, z]")
        if len(self.rotation) != 3:
            raise ValueError("CreateLightInput.rotation must have exactly 3 values [x, y, z] (radians)")

        self.color = _coerce_color(self.color, "CreateLightInput.color")
        _validate_rgb(self.color, "CreateLightInput.color")
        self.color = [float(c) for c in self.color[:3]]

        self.energy = _coerce_number(self.energy, "CreateLightInput.energy")
        if not (0.0 <= self.energy <= 1_000_000.0):
            raise ValueError("CreateLightInput.energy must be a number between 0 and 1,000,000")
        self.size = _coerce_number(self.size, "CreateLightInput.size")
        if self.size < 0:
            raise ValueError("CreateLightInput.size must be a non-negative number")
        self.spot_angle = _coerce_number(self.spot_angle, "CreateLightInput.spot_angle")
        if not (1.0 <= self.spot_angle <= 180.0):
            raise ValueError("CreateLightInput.spot_angle must be between 1 and 180 degrees")


@dataclass
class SetWorldInput:
    """world.set tool ke liye input contract (background colour + ambient strength)."""
    color: Optional[List[float]] = None
    strength: Optional[float] = None

    def __post_init__(self):
        if self.color is None and self.strength is None:
            raise ValueError("SetWorldInput requires at least one of: color, strength")
        if self.color is not None:
            self.color = _coerce_color(self.color, "SetWorldInput.color")
            _validate_rgb(self.color, "SetWorldInput.color")
            self.color = [float(c) for c in self.color[:3]]
        if self.strength is not None:
            self.strength = _coerce_number(self.strength, "SetWorldInput.strength")
            if not (0.0 <= self.strength <= 100.0):
                raise ValueError("SetWorldInput.strength must be a number between 0.0 and 100.0")


# ---------------------------------------------------------
# Curves + Model library
# ---------------------------------------------------------
CURVE_TYPES = ("BEZIER", "POLY", "NURBS")
CURVE_PRESETS = ("line", "circle", "arc", "spiral", "wave")


def _preset_points(preset, radius, length, height, turns, amplitude, waves, angle_degrees, segments):
    """Hinglish: LLM ko coordinates guess na karne pade — common shapes ke points yahin ban jaate hain."""
    import math

    if preset == "line":
        return [[0.0, 0.0, 0.0], [length, 0.0, 0.0]]
    if preset == "circle":
        return [[radius * math.cos(2 * math.pi * i / segments), radius * math.sin(2 * math.pi * i / segments), 0.0]
                for i in range(segments)]
    if preset == "arc":
        end = math.radians(angle_degrees)
        return [[radius * math.cos(end * i / segments), radius * math.sin(end * i / segments), 0.0]
                for i in range(segments + 1)]
    if preset == "spiral":  # helix: upar chadhti hui gol curve
        n = max(8, int(turns * segments) + 1)
        return [[radius * math.cos(2 * math.pi * turns * i / (n - 1)),
                 radius * math.sin(2 * math.pi * turns * i / (n - 1)),
                 height * i / (n - 1)] for i in range(n)]
    if preset == "wave":
        n = max(5, int(waves * 4) + 1)
        return [[length * i / (n - 1), amplitude * math.sin(2 * math.pi * waves * i / (n - 1)), 0.0]
                for i in range(n)]
    raise ValueError(f"unknown preset '{preset}'")


@dataclass
class CreateCurveInput:
    """
    curve.create tool ke liye input contract.

    Ya to `points` do ([[x,y,z], ...] ya [[x,y,z,radius], ...]), ya `preset`
    (line/circle/arc/spiral/wave). `radius` har point par thickness ko ghata-badha sakta hai
    (tapered flame/branch/horn banane ke liye).
    """
    name: str
    points: Optional[List[List[float]]] = None
    preset: Optional[str] = None
    curve_type: str = "BEZIER"
    thickness: float = 0.05
    closed: bool = False
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    fill_caps: bool = True
    resolution: int = 12
    # preset parameters
    radius: float = 1.0
    length: float = 2.0
    height: float = 1.0
    turns: float = 3.0
    amplitude: float = 0.3
    waves: float = 3.0
    angle_degrees: float = 180.0
    segments: int = 8

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CreateCurveInput.name must be a non-empty string")

        self.curve_type = str(self.curve_type).upper()
        if self.curve_type not in CURVE_TYPES:
            raise ValueError(f"CreateCurveInput.curve_type must be one of {list(CURVE_TYPES)}, got '{self.curve_type}'")

        self.thickness = _coerce_number(self.thickness, "CreateCurveInput.thickness")
        if not (0.0 <= self.thickness <= 10.0):
            raise ValueError("CreateCurveInput.thickness must be between 0 and 10")
        self.closed = _coerce_bool(self.closed, "CreateCurveInput.closed")
        self.fill_caps = _coerce_bool(self.fill_caps, "CreateCurveInput.fill_caps")
        self.resolution = _coerce_number(self.resolution, "CreateCurveInput.resolution", integer=True)
        if not (1 <= self.resolution <= 64):
            raise ValueError("CreateCurveInput.resolution must be an integer between 1 and 64")

        for attr in ("location", "rotation", "scale"):
            values = _coerce_list(getattr(self, attr), f"CreateCurveInput.{attr}")
            if len(values) != 3:
                raise ValueError(f"CreateCurveInput.{attr} must have exactly 3 values [x, y, z]")
            setattr(self, attr, values)

        for attr in ("radius", "length", "height", "turns", "amplitude", "waves", "angle_degrees"):
            setattr(self, attr, _coerce_number(getattr(self, attr), f"CreateCurveInput.{attr}"))
        self.segments = _coerce_number(self.segments, "CreateCurveInput.segments", integer=True)
        if not (3 <= self.segments <= 64):
            raise ValueError("CreateCurveInput.segments must be an integer between 3 and 64")

        if self.points is None and self.preset is None:
            raise ValueError("CreateCurveInput requires either `points` or a `preset` "
                             f"({', '.join(CURVE_PRESETS)})")

        if self.points is not None:
            raw = to_plain(self.points)
            if not isinstance(raw, list) or len(raw) < 2:
                raise ValueError("CreateCurveInput.points must be a list of at least 2 points [[x, y, z], ...]")
            cleaned = []
            for point in raw:
                coords = _coerce_list(point, "CreateCurveInput.points")
                if len(coords) not in (3, 4):
                    raise ValueError("each point in CreateCurveInput.points must be [x, y, z] or [x, y, z, radius]")
                cleaned.append(coords)
            self.points = cleaned
        else:
            self.preset = str(self.preset).lower()
            if self.preset not in CURVE_PRESETS:
                raise ValueError(f"CreateCurveInput.preset must be one of {list(CURVE_PRESETS)}, got '{self.preset}'")
            self.points = _preset_points(self.preset, self.radius, self.length, self.height, self.turns,
                                         self.amplitude, self.waves, self.angle_degrees, self.segments)
            if self.preset == "circle":
                self.closed = True


@dataclass
class ListLibraryInput:
    """library.list tool ke liye input contract."""
    category: Optional[str] = None

    def __post_init__(self):
        if self.category is not None:
            self.category = str(self.category).strip().lower() or None


@dataclass
class PlaceModelInput:
    """
    library.place tool ke liye input contract — library ke ek ready-made model
    (campfire, pine_tree, tent...) ko scene mein ek hi call se banata hai.
    """
    model: str
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: float = 1.0
    yaw_degrees: float = 0.0
    prefix: str = ""
    colors: Optional[dict] = None

    def __post_init__(self):
        if not self.model or not isinstance(self.model, str):
            raise ValueError("PlaceModelInput.model must be a non-empty string")
        self.model = self.model.strip().lower().replace(" ", "_").replace("-", "_")

        self.location = _coerce_list(self.location, "PlaceModelInput.location")
        if len(self.location) != 3:
            raise ValueError("PlaceModelInput.location must have exactly 3 values [x, y, z]")

        self.scale = _coerce_number(self.scale, "PlaceModelInput.scale")
        if not (0.05 <= self.scale <= 50.0):
            raise ValueError("PlaceModelInput.scale must be between 0.05 and 50")
        self.yaw_degrees = _coerce_number(self.yaw_degrees, "PlaceModelInput.yaw_degrees")

        if not isinstance(self.prefix, str):
            raise ValueError("PlaceModelInput.prefix must be a string")

        if self.colors is not None:
            plain = to_plain(self.colors)
            if not isinstance(plain, dict):
                raise ValueError("PlaceModelInput.colors must be an object like {\"leaves\": [0.1, 0.4, 0.1]}")
            self.colors = {str(k): _coerce_color(v, f"PlaceModelInput.colors[{k}]")[:3] for k, v in plain.items()}


# ---------------------------------------------------------
# Downloaded (local) GitHub CC0 models
# ---------------------------------------------------------
@dataclass
class SearchLocalAssetsInput:
    """asset.search_local ke liye input contract."""
    query: str
    limit: int = 8
    project: Optional[str] = None

    def __post_init__(self):
        if not self.query or not isinstance(self.query, str) or not self.query.strip():
            raise ValueError("SearchLocalAssetsInput.query must be a non-empty string")
        self.query = self.query.strip()
        self.limit = _coerce_number(self.limit, "SearchLocalAssetsInput.limit", integer=True)
        if not (1 <= self.limit <= 30):
            raise ValueError("SearchLocalAssetsInput.limit must be an integer between 1 and 30")
        if self.project is not None:
            self.project = str(self.project).strip().lower() or None


@dataclass
class PlaceLocalAssetInput:
    """asset.place_local ke liye input contract — `asset_id` YA `query` do."""
    asset_id: Optional[str] = None
    query: Optional[str] = None
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: float = 1.0
    yaw_degrees: float = 0.0

    def __post_init__(self):
        if not (self.asset_id and str(self.asset_id).strip()) and not (self.query and str(self.query).strip()):
            raise ValueError("PlaceLocalAssetInput requires `asset_id` (from asset.search_local) or `query`")
        self.asset_id = str(self.asset_id).strip() if self.asset_id else None
        self.query = str(self.query).strip() if self.query else None
        self.location = _coerce_list(self.location, "PlaceLocalAssetInput.location")
        if len(self.location) != 3:
            raise ValueError("PlaceLocalAssetInput.location must have exactly 3 values [x, y, z]")
        self.scale = _coerce_number(self.scale, "PlaceLocalAssetInput.scale")
        if not (0.01 <= self.scale <= 100.0):
            raise ValueError("PlaceLocalAssetInput.scale must be between 0.01 and 100")
        self.yaw_degrees = _coerce_number(self.yaw_degrees, "PlaceLocalAssetInput.yaw_degrees")


# ---------------------------------------------------------
# Vectors + image paths (existing tools ko bhi lenient banane ke liye)
# ---------------------------------------------------------
def _vec3(value, label):
    """[x, y, z] chahiye. "1, 2, 3", {"x","y","z"}, proto list, ints/floats sab chalte hain."""
    plain = to_plain(value)
    try:
        coords = _coerce_list(plain, label)
    except ValueError:
        coords = None
    if coords is None or len(coords) != 3:
        shown = repr(plain)
        if len(shown) > 80:
            shown = shown[:80] + "..."
        raise ValueError(f"{label} must have exactly 3 values [x, y, z] (got {shown})")
    return coords


# ---------------------------------------------------------
# Custom mesh (vertices + faces)
# ---------------------------------------------------------
@dataclass
class CreateMeshInput:
    """
    mesh.create tool ke liye input contract — apna khud ka shape (triangle, wedge, roof, ramp...)
    vertices + faces se banao. Primitives (cube/cone...) jo nahi bana sakte, wo yahan se.

    vertices : [[x,y,z], ...]       (kam se kam 3)
    faces    : [[i,j,k,...], ...]   har face vertices ke index (0 se shuru), kam se kam 3 alag index
    """
    name: str
    vertices: List[List[float]]
    faces: List[List[int]]
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: List[float] = field(default_factory=lambda: [1.0, 1.0, 1.0])
    shade_smooth: bool = False

    MAX_ELEMENTS = 5000

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CreateMeshInput.name must be a non-empty string")

        raw_vertices = to_plain(self.vertices)
        if not isinstance(raw_vertices, list) or len(raw_vertices) < 3:
            raise ValueError("CreateMeshInput.vertices must be a list of at least 3 points [[x, y, z], ...]")
        if len(raw_vertices) > self.MAX_ELEMENTS:
            raise ValueError(f"CreateMeshInput.vertices has too many points (max {self.MAX_ELEMENTS})")
        self.vertices = [_vec3(v, "CreateMeshInput.vertices[]") for v in raw_vertices]

        raw_faces = to_plain(self.faces)
        if not isinstance(raw_faces, list) or not raw_faces:
            raise ValueError("CreateMeshInput.faces must be a non-empty list of index lists like [[0, 1, 2]]")
        if len(raw_faces) > self.MAX_ELEMENTS:
            raise ValueError(f"CreateMeshInput.faces has too many faces (max {self.MAX_ELEMENTS})")

        cleaned = []
        for number, face in enumerate(raw_faces):
            indices = _coerce_list(face, "CreateMeshInput.faces[]")
            indices = [_coerce_number(i, "CreateMeshInput.faces[]", integer=True) for i in indices]
            if len(indices) < 3 or len(set(indices)) != len(indices):
                raise ValueError(f"CreateMeshInput.faces[{number}] needs at least 3 different vertex indices, got {indices}")
            if any(i < 0 or i >= len(self.vertices) for i in indices):
                raise ValueError(
                    f"CreateMeshInput.faces[{number}] uses a vertex index outside 0..{len(self.vertices) - 1}: {indices}")
            cleaned.append(indices)
        self.faces = cleaned

        self.location = _vec3(self.location, "CreateMeshInput.location")
        self.rotation = _vec3(self.rotation, "CreateMeshInput.rotation")
        self.scale = _vec3(self.scale, "CreateMeshInput.scale")
        self.shade_smooth = _coerce_bool(self.shade_smooth, "CreateMeshInput.shade_smooth")


# ---------------------------------------------------------
# Mesh damage (broken / chipped / dented / rough)
# ---------------------------------------------------------
_REGION_SYNONYMS = {
    "upper": "top", "above": "top", "up": "top", "tip": "top", "neck": "top", "head": "top", "crown": "top",
    "lid": "top", "rim": "top", "mouth": "top", "opening": "top",
    "lower": "bottom", "base": "bottom", "down": "bottom", "foot": "bottom", "under": "bottom",
    "right side": "right", "left side": "left", "whole": "all", "entire": "all", "everywhere": "all", "full": "all",
}
_STYLE_SYNONYMS = {
    "break": "broken", "shattered": "broken", "shatter": "broken", "cracked": "broken", "crack": "broken",
    "damaged": "broken", "damage": "broken", "smashed": "broken", "jagged": "broken", "snapped": "broken",
    "chip": "chipped", "chipping": "chipped", "notched": "chipped",
    "dent": "dented", "dents": "dented", "crushed": "dented", "squashed": "dented", "bent": "dented",
    "worn": "rough", "scratched": "rough", "weathered": "rough", "bumpy": "rough", "old": "rough", "aged": "rough",
}


@dataclass
class DamageMeshInput:
    """
    mesh.damage tool ke liye input contract — kisi bhi mesh ka ek hissa toota/chipped/pichka/khurdura banata hai.

    region   : top | bottom | left | right | front | back | all   ("neck", "lid", "rim" -> top; "base" -> bottom)
    style    : broken | chipped | dented | rough                  ("cracked", "shattered" -> broken)
    portion  : region object ki kitni lambai ko cover kare (0.02-1.0, default 0.25 = upar ka chautha hissa)
    strength : kitna kharab (0.01-0.6, default 0.15 = halka sa)
    detail   : extra mesh-cuts (0-2) taaki low-poly model mein toot ka asar saaf dikhe
    """
    object_name: str
    region: str = "top"
    style: str = "broken"
    portion: float = 0.25
    strength: float = 0.15
    seed: int = 1
    detail: int = 1

    def __post_init__(self):
        from .mesh_damage import REGIONS, STYLES

        if not self.object_name or not isinstance(self.object_name, str):
            raise ValueError("DamageMeshInput.object_name must be a non-empty string")

        region = str(self.region).strip().lower().replace("_", " ")
        self.region = _REGION_SYNONYMS.get(region, region)
        if self.region not in REGIONS:
            raise ValueError(f"DamageMeshInput.region must be one of {list(REGIONS)}, got '{self.region}'")

        style = str(self.style).strip().lower()
        self.style = _STYLE_SYNONYMS.get(style, style)
        if self.style not in STYLES:
            raise ValueError(f"DamageMeshInput.style must be one of {list(STYLES)}, got '{self.style}'")

        self.portion = _coerce_number(self.portion, "DamageMeshInput.portion")
        if not (0.02 <= self.portion <= 1.0):
            raise ValueError("DamageMeshInput.portion must be between 0.02 and 1.0")
        self.strength = _coerce_number(self.strength, "DamageMeshInput.strength")
        if not (0.01 <= self.strength <= 0.6):
            raise ValueError("DamageMeshInput.strength must be between 0.01 and 0.6")
        self.seed = _coerce_number(self.seed, "DamageMeshInput.seed", integer=True)
        self.detail = _coerce_number(self.detail, "DamageMeshInput.detail", integer=True)
        if not (0 <= self.detail <= 2):
            raise ValueError("DamageMeshInput.detail must be 0, 1 or 2")