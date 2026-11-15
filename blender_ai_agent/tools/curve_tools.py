"""Curve Tools"""

import re

from .base import Permission, Tool, ToolResult
from .models import CreateCurveInput
from . import paths as _paths
from .ribbon import centre_line, strokes_mesh

# Names that mean "something you walk or drive on": a round tube is never right for these.
_NOT_A_PATH = re.compile(r"ground|floor|lawn|terrain|grass|base|field|plaza|pool|water|pond|lake|river|deck|patio",
                         re.IGNORECASE)
_MARKING = re.compile(r"line|marking|stripe|crease|circle|spot|area|box|arc|border|edge|touch|halfway|boundary|"
                      r"court|pitch|rink|lane_line|paint", re.IGNORECASE)
_GROUND_STRIP = re.compile(r"path|road|walk|trail|street|lane|pavement|sidewalk|driveway|footway|track|runway",
                           re.IGNORECASE)


class CreateCurveTool(Tool):
    name = "curve.create"
    description = (
        "Creates a smooth curve object with real thickness (a tube). Give EITHER `points` "
        "([[x,y,z], ...] or [[x,y,z,radius], ...] - radius 0-1 per point tapers the thickness, "
        "e.g. [[0,0,0,1],[0.1,0,0.5,0.6],[0.2,0,1,0.1]] makes a flame tongue / horn / branch that "
        "ends in a point) OR a `preset`: line (length), circle (radius), arc (radius, angle_degrees), "
        "spiral (radius, height, turns - a spring/helix), wave (length, amplitude, waves). "
        "curve_type BEZIER (smooth, default), POLY (straight segments - ropes, pipes, fences) or "
        "NURBS. `thickness` is the tube radius in metres (0.01 rope, 0.05 cable, 0.1 branch); 0 makes "
        "a bare wire. Set `closed` true for loops (rings, tracks). Position it with location/rotation/scale, "
        "then colour it with material.create + material.assign like any object. "
        "PATHS, ROADS, SIDEWALKS, TRACKS: use profile='flat' with `width` in metres (a 2 m path -> width 2) - "
        "this makes a thin flat strip lying on the ground instead of a tube. For an X, a T junction or several "
        "separate lines in one object give `strokes` ([[[x,y,z],...], [[x,y,z],...]]) instead of one long "
        "`points` list, otherwise the end of one line is joined to the start of the next."
    )
    permission = Permission.SAFE_WRITE
    input_model = CreateCurveInput

    def __init__(self, bridge):
        self._bridge = bridge

    @staticmethod
    def _flat_settings(v: CreateCurveInput):
        """(is_flat, width). Explicit profile wins; otherwise a thick curve named like a path/road is flat."""
        if v.profile == "flat":
            return True, (v.width or max(v.thickness * 2.0, 1.0))
        if v.profile == "round":
            return False, 0.0
        if _GROUND_STRIP.search(v.name or "") and (v.width > 0 or v.thickness >= 0.2):
            return True, (v.width or v.thickness * 2.0)
        return False, 0.0

    def _run_flat(self, v: CreateCurveInput, width: float) -> ToolResult:
        strokes = v.strokes or [v.points]
        smooth = v.curve_type != "POLY"
        verts, faces = strokes_mesh(strokes, width=width, depth=0.02, closed=v.closed,
                                    smooth=smooth, samples=max(2, min(v.resolution, 8)))
        if not faces:
            return ToolResult.fail("curve.create: the path points are all in one spot - give points that are apart.")
        obj = self._bridge.create_mesh(name=v.name, vertices=verts, faces=faces, location=v.location,
                                       rotation=v.rotation, scale=v.scale)
        self._remember_path(obj.name, v, strokes, width, smooth)
        return ToolResult.ok({
            "name": obj.name,
            "profile": "flat",
            "width": round(width, 3),
            "strokes": len(strokes),
            "point_count": sum(len(st) for st in strokes),
            "closed": v.closed,
            "location": list(obj.location),
            "note": "Flat strip (a mesh) lying on the ground; colour it with material.recipe / material.assign.",
        })

    @staticmethod
    def _remember_path(name: str, v: CreateCurveInput, strokes, width: float, smooth: bool) -> None:
        """Walkable strips (not a ground sheet or a pool) go on the path map so props are kept off them."""
        named_path = bool(_GROUND_STRIP.search(name))
        if _MARKING.search(name) or width < 0.6:
            return                       # painted lines, creases, borders: thin markings, not something to walk on
        if _NOT_A_PATH.search(name) and not named_path:
            return
        if width > (12.0 if named_path else 6.0):
            return
        centre_lines = [centre_line(stroke, v.closed, smooth, max(2, min(v.resolution, 8))) for stroke in strokes]
        _paths.register(name, centre_lines, width, v.location, v.rotation, v.scale)

    def run(self, validated_input: CreateCurveInput) -> ToolResult:
        flat, width = self._flat_settings(validated_input)
        if flat and hasattr(self._bridge, "create_mesh"):
            return self._run_flat(validated_input, width)

        extra = {}
        if validated_input.strokes and len(validated_input.strokes) > 1:
            extra["strokes"] = validated_input.strokes
        obj = self._bridge.create_curve(**extra,
            name=validated_input.name,
            points=validated_input.points,
            curve_type=validated_input.curve_type,
            thickness=validated_input.thickness,
            closed=validated_input.closed,
            location=validated_input.location,
            rotation=validated_input.rotation,
            scale=validated_input.scale,
            fill_caps=validated_input.fill_caps,
            resolution=validated_input.resolution,
        )

        return ToolResult.ok({
            "name": obj.name,
            "curve_type": validated_input.curve_type,
            "point_count": len(validated_input.points),
            "strokes": len(validated_input.strokes or [validated_input.points]),
            "thickness": validated_input.thickness,
            "closed": validated_input.closed,
            "location": list(obj.location),
        })