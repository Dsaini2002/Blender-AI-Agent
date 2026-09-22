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

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("ModifyMaterialInput.name must be a non-empty string")
        if self.color is not None and len(self.color) not in (3, 4):
            raise ValueError("ModifyMaterialInput.color must have 3 (RGB) or 4 (RGBA) values")
        if self.roughness is not None and not (0.0 <= self.roughness <= 1.0):
            raise ValueError("ModifyMaterialInput.roughness must be between 0.0 and 1.0")
        if self.metallic is not None and not (0.0 <= self.metallic <= 1.0):
            raise ValueError("ModifyMaterialInput.metallic must be between 0.0 and 1.0")
        if self.color is None and self.roughness is None and self.metallic is None:
            raise ValueError("ModifyMaterialInput requires at least one of: color, roughness, metallic")
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