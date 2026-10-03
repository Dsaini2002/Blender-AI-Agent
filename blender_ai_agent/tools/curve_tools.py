"""
Curve Tools
============
Hinglish: Ab sirf cube/sphere/cone nahi — curves bhi. Rope, pipe, cable, tree branch,
tapered flame, horn, road/path, spring (spiral), wave... sab smooth curve se banta hai.

`points` ke har point mein optional 4th value `radius` hota hai: bevel (thickness) us jagah
utna ghata/badha — isi se patle sire wale (tapered) shapes bante hain.
"""

from .base import Permission, Tool, ToolResult
from .models import CreateCurveInput


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
        "then colour it with material.create + material.assign like any object."
    )
    permission = Permission.SAFE_WRITE
    input_model = CreateCurveInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: CreateCurveInput) -> ToolResult:
        obj = self._bridge.create_curve(
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
            "thickness": validated_input.thickness,
            "closed": validated_input.closed,
            "location": list(obj.location),
        })