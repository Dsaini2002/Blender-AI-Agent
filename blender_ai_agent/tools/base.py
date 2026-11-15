"""Tool (abstract base class)"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generic, Optional, Type, TypeVar

from ..input_coercion import coerce_arguments


class Permission(str, Enum):
    READ_ONLY = "read_only"
    SAFE_WRITE = "safe_write"     # object.create — reversible, low risk
    DESTRUCTIVE = "destructive"
    PYTHON_EXECUTION = "python_execution"

@dataclass
class ToolResult:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @staticmethod
    def ok(data: Dict[str, Any] = None) -> "ToolResult":
        return ToolResult(success=True, data=data or {})

    @staticmethod
    def fail(error: str) -> "ToolResult":
        return ToolResult(success=False, error=error)


TInput = TypeVar("TInput")


class Tool(ABC, Generic[TInput]):

    name: str = ""
    description: str = ""
    permission: Permission = Permission.SAFE_WRITE
    input_model: Optional[Type[Any]] = None
    # Creation tools give a missing `name` this default (Blender adds .001 if it is taken), so a forgotten
    # name is not a failed call. Never set on tools whose `name` points at an existing object.
    auto_name: Optional[str] = None

    def validate(self, input_data: Dict[str, Any]) -> TInput:
        if self.input_model is None:
            return input_data  # type: ignore

        normalized_input = self._normalize_input(input_data or {})
        normalized_input = coerce_arguments(self.input_model, normalized_input)

        try:
            return self.input_model(**normalized_input)
        except (TypeError, AttributeError, KeyError, IndexError) as exc:
            raise ValueError(f"Invalid input for tool '{self.name}': {exc}{self._argument_hint(input_data or {})}") from exc
        except ValueError:
            raise

    # ---------------------------------------------------------
    # Common aliases models mistakenly use instead of the real field name.
    # Only applied when the real field name doesn't already have a value.
    # ---------------------------------------------------------
    _FIELD_ALIASES = {
        "type": ("primitive", "object_type"),
        "shape": ("primitive",),
        "kind": ("primitive",),
        "object_name": ("name",),
        "position": ("location",),
        # retopology / lighting
        "target_face_count": ("target_faces",),
        "face_count": ("target_faces",),
        "faces": ("target_faces",),
        "poly_count": ("target_faces",),
        "ratio": ("decimate_ratio",),
        "intensity": ("energy",),
        "power": ("energy",),
        "brightness": ("energy",),
        "type_of_light": ("light_type",),
        # object / material references
        "object": ("object_name", "name"),
        "obj": ("object_name", "name"),
        "target": ("object_name", "name"),
        "target_object": ("object_name", "name"),
        "mesh": ("object_name", "name"),
        "objects": ("names", "assign_to", "object_names"),
        "object_names": ("names", "assign_to"),
        "targets": ("names", "assign_to"),
        "material": ("material_name",),
        "mat": ("material_name",),
        "material_id": ("material_name",),
        "name": ("prefix", "object_name"),
        "name_prefix": ("prefix",),
        "points": ("profile", "polygon"),
        "resolution": ("segments",),
        "steps": ("segments",),
        "height_m": ("height",),
    }

    def _argument_hint(self, input_data: Dict[str, Any]) -> str:
        """Tell the model which argument names are valid and which ones it sent were ignored."""
        import dataclasses

        if not dataclasses.is_dataclass(self.input_model):
            return ""
        valid = [f.name for f in dataclasses.fields(self.input_model)]
        unknown = [k for k in input_data if k not in valid]
        hint = f". Valid arguments: {', '.join(valid)}"
        if unknown:
            hint += f". Ignored unknown arguments: {', '.join(unknown)}"
        return hint

    def _normalize_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        import dataclasses

        if not dataclasses.is_dataclass(self.input_model):
            return input_data

        valid_fields = {f.name for f in dataclasses.fields(self.input_model)}
        normalized: Dict[str, Any] = {}

        for key, value in input_data.items():
            if key in valid_fields:
                normalized[key] = value
                continue

            aliases = tuple(self._FIELD_ALIASES.get(key, ())) + self._derived_aliases(key)
            target = next((a for a in aliases if a in valid_fields and a not in normalized
                           and a not in input_data), None)
            if target is not None:
                normalized[target] = value

        if self.auto_name and "name" in valid_fields and not normalized.get("name"):
            normalized["name"] = self.auto_name
        return normalized

    @staticmethod
    def _derived_aliases(key: str):
        """object -> object_name, material_names -> materials, ... (only used when nothing else matches)."""
        out = [f"{key}_name", f"{key}_names"]
        if key.endswith("_name"):
            out.append(key[:-5])
        if key.endswith("_names"):
            out.append(key[:-6] + "s")
        if "_" in key:                                   # light_location -> location, camera_rotation -> rotation
            out.append(key.split("_", 1)[1])
            out.append(key.rsplit("_", 1)[1])
        return tuple(out)

    @abstractmethod
    def run(self, validated_input: TInput) -> ToolResult:
        raise NotImplementedError

    def execute(self, input_data: Dict[str, Any] = None) -> ToolResult:
        try:
            validated = self.validate(input_data or {})
        except ValueError as exc:
            return ToolResult.fail(str(exc))
        except Exception as exc:  # noqa: BLE001 
            return ToolResult.fail(f"Invalid input for tool '{self.name}': {exc}")

        try:
            return self.run(validated)
        except Exception as exc:
            return ToolResult.fail(f"Tool '{self.name}' failed: {exc}")