"""object.recolor: change the colour of what is already in the scene ('make the walls cream', 'sofa ko laal karo')."""

import fnmatch
import re
from dataclasses import dataclass
from typing import Any, List

from .base import Permission, Tool, ToolResult
from .colors import parse_color
from .models import _coerce_bool


_TRIM = re.compile(r"leg|feet|foot|handle|knob|hinge|screen|bulb|light|lamp|glass|rim|wheel|tyre|tire|base|stand|bolt")


@dataclass
class RecolorInput:
    names: Any = None
    color: Any = None
    keep_texture: bool = True

    def __post_init__(self):
        names = self.names
        if isinstance(names, str):
            names = [n.strip() for n in names.replace(";", ",").split(",") if n.strip()]
        if not names:
            raise ValueError("RecolorInput.names: which objects? e.g. ['sofa*'] or ['hostel_walls']")
        self.names = [str(n) for n in names]
        self.color = parse_color(self.color, "RecolorInput.color")
        if self.color is None:
            raise ValueError("RecolorInput.color is required: a colour word ('sky blue', 'cream', 'laal') or [r, g, b]")
        self.keep_texture = _coerce_bool(self.keep_texture, "RecolorInput.keep_texture")


def resolve_names(patterns: List[str], scene_names: List[str], trim: bool = True) -> List[str]:
    """Exact names, * patterns, a library item ('bookshelf.001' = every part of that copy) or a model prefix
    ('sofa' -> the sofa body; with trim=False also its feet)."""
    found: List[str] = []
    lower = {n.lower(): n for n in scene_names}
    try:
        from ..agent.scene_checks import library_items
        items = {k.lower(): v for k, v in library_items(scene_names).items()}
    except Exception:  # noqa: BLE001
        items = {}
    for pattern in patterns:
        key = pattern.lower()
        if key in lower:
            hits = [lower[key]]
        elif not trim and key in items:
            hits = list(items[key])
        elif any(c in key for c in "*?["):
            hits = [n for n in scene_names if fnmatch.fnmatch(n.lower(), key)]
        else:
            hits = [n for n in scene_names if n.lower().startswith(key + "_") or n.lower().startswith(key + ".")]
            if trim:
                main = [n for n in hits if not _TRIM.search(n[len(key):].lower())]
                hits = main or hits              # 'sofa' -> the sofa body, not its wooden feet
        for hit in hits:
            if hit not in found:
                found.append(hit)
    return found


class RecolorTool(Tool):
    name = "object.recolor"
    description = (
        "Changes the COLOUR of objects that already exist - the tool for 'make the walls cream', 'change the sofa to "
        "blue', 'roof laal karo'. names = exact object names, * patterns ('hostel_walls', 'sofa*', '*_curtains*') or "
        "a model prefix ('sofa' = every sofa_ part); color = a colour word (white, cream, beige, sky blue, navy, "
        "maroon, terracotta, mint, golden, laal, neela ...) or [r, g, b] 0-1. Wood / fabric / brick textures keep "
        "their pattern (keep_texture=false gives a plain colour). Only the named objects change, even when their "
        "material is shared. For a building made by mesh.building you can also call mesh.building again with "
        "wall_color / roof_color / accent_color."
    )
    permission = Permission.SAFE_WRITE
    input_model = RecolorInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: RecolorInput) -> ToolResult:
        scene = [getattr(o, "name", "") for o in self._bridge.get_objects()]
        targets = resolve_names(v.names, scene)
        if not targets:
            close = [n for n in scene if any(p.strip("*").lower()[:4] in n.lower() for p in v.names)][:12]
            return ToolResult.fail(f"No object matches {v.names}." + (f" Close names: {close}" if close else
                                                                    " Call scene.inspect to see the names."))
        changed, skipped = [], []
        for name in targets:
            obj = self._bridge.get_object(name)
            if obj is not None and str(getattr(obj, "type", "MESH")).upper() in ("LIGHT", "CAMERA", "EMPTY"):
                skipped.append(name)
                continue
            try:
                if hasattr(self._bridge, "recolor_object"):
                    self._bridge.recolor_object(name, v.color, keep_texture=v.keep_texture, others=targets)
                else:                                         # simple bridges: a plain material per object
                    material = self._bridge.create_material(name=f"{name}_color", color=v.color)
                    self._bridge.assign_material(name, getattr(material, "name", f"{name}_color"))
                changed.append(name)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"{name} ({exc})")
        if not changed:
            return ToolResult.fail(f"Could not recolour {skipped}")
        return ToolResult.ok({"recolored": changed, "color": [round(c, 3) for c in v.color[:3]],
                              "skipped": skipped, "note": "Done - the shape and the rest of the scene are unchanged."})


@dataclass
class MoveByInput:
    names: Any = None
    offset: Any = None

    def __post_init__(self):
        names = self.names
        if isinstance(names, str):
            names = [n.strip() for n in names.replace(";", ",").split(",") if n.strip()]
        if not names:
            raise ValueError("MoveByInput.names: which objects? e.g. ['wardrobe'] (every wardrobe_ part)")
        self.names = [str(n) for n in names]
        try:
            offset = [float(v) for v in list(self.offset)]
        except (TypeError, ValueError):
            raise ValueError("MoveByInput.offset must be [dx, dy, dz] in metres") from None
        if len(offset) == 2:
            offset.append(0.0)
        if len(offset) != 3:
            raise ValueError("MoveByInput.offset must be [dx, dy, dz] in metres")
        if max(abs(v) for v in offset) > 500:
            raise ValueError("MoveByInput.offset is more than 500 m - give metres")
        self.offset = offset


class MoveByTool(Tool):
    name = "object.move_by"
    description = (
        "Moves objects BY an offset [dx, dy, dz] in metres, keeping their shape and turn - the tool for 'move the "
        "wardrobe 40 cm left' and for the automatic check's 'move every part of X by [..]'. names = a library model "
        "('wardrobe', 'bookshelf.001' = every part of that copy), exact names or * patterns. All parts move "
        "together, so a model never comes apart."
    )
    permission = Permission.SAFE_WRITE
    input_model = MoveByInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: MoveByInput) -> ToolResult:
        scene = [getattr(o, "name", "") for o in self._bridge.get_objects()]
        targets = resolve_names(v.names, scene, trim=False)
        if not targets:
            return ToolResult.fail(f"No object matches {v.names}. Call scene.inspect to see the names.")
        moved = []
        for name in targets:
            obj = self._bridge.get_object(name)
            if obj is None:
                continue
            location = [float(c) for c in list(getattr(obj, "location", [0.0, 0.0, 0.0]))[:3]]
            new = [round(location[k] + v.offset[k], 4) for k in range(3)]
            if self._bridge.transform_object(name, location=new) is not None:
                moved.append(name)
        if not moved:
            return ToolResult.fail(f"Could not move {targets}")
        return ToolResult.ok({"moved": moved, "offset": v.offset})
