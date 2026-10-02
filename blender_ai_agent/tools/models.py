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

        if len(self.location) != 3:
            raise ValueError("CreateObjectInput.location must have exactly 3 values [x, y, z]")


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

        for field_name, value in (
            ("location", self.location),
            ("rotation", self.rotation),
            ("scale", self.scale),
        ):
            if value is not None and len(value) != 3:
                raise ValueError(f"TransformObjectInput.{field_name} must have exactly 3 values [x, y, z]")

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
        if self.color is not None and len(self.color) not in (3, 4):
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
            self.emission_color = _coerce_list(self.emission_color, "ModifyMaterialInput.emission_color")
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
        if self.color is not None and len(self.color) not in (3, 4):
            raise ValueError("ModifyMaterialInput.color must have 3 (RGB) or 4 (RGBA) values")
        if self.roughness is not None and not (0.0 <= self.roughness <= 1.0):
            raise ValueError("ModifyMaterialInput.roughness must be between 0.0 and 1.0")
        if self.metallic is not None and not (0.0 <= self.metallic <= 1.0):
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
        if self.location is not None and len(self.location) != 3:
            raise ValueError("CreateCameraInput.location must have exactly 3 values [x, y, z]")
        if self.rotation is not None and len(self.rotation) != 3:
            raise ValueError("CreateCameraInput.rotation must have exactly 3 values [x, y, z]")


@dataclass
class SetCameraInput:
    """camera.set tool ke liye input contract."""
    name: str

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("SetCameraInput.name must be a non-empty string")


@dataclass
class RenderPreviewInput:
    """render.preview tool ke liye input contract."""
    filepath: str

    def __post_init__(self):
        if not self.filepath or not isinstance(self.filepath, str):
            raise ValueError("RenderPreviewInput.filepath must be a non-empty string")

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
    if isinstance(value, str):
        cleaned = value.strip().strip("[]()")
        parts = [p for p in cleaned.replace(";", ",").split(",") if p.strip()]
        value = parts
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list of numbers")
    return [_coerce_number(v, label) for v in value]


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

        self.color = _coerce_list(self.color, "CreateLightInput.color")
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
            self.color = _coerce_list(self.color, "SetWorldInput.color")
            _validate_rgb(self.color, "SetWorldInput.color")
            self.color = [float(c) for c in self.color[:3]]
        if self.strength is not None:
            self.strength = _coerce_number(self.strength, "SetWorldInput.strength")
            if not (0.0 <= self.strength <= 100.0):
                raise ValueError("SetWorldInput.strength must be a number between 0.0 and 100.0")
