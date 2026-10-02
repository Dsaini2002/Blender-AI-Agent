"""
Lighting + World Tools
=======================
Hinglish: Scene ka "mood" yahin se aata hai — light.create (point/sun/spot/
area, colour, energy) aur world.set (background colour + ambient strength).
Pehle agent sirf shapes bana sakta tha; ab night scene, campfire glow,
rim lights sab possible hain. Raw bpy yahan nahi — sirf BlenderBridge.
"""

from .base import Permission, Tool, ToolResult
from .models import CreateLightInput, SetWorldInput


class CreateLightTool(Tool):
    name = "light.create"
    description = (
        "Creates a light with colour and brightness. light_type: POINT (bulb/campfire/lantern, "
        "energy in Watts e.g. 300-1000), SUN (moonlight/sunlight, energy is strength e.g. 0.3-5, "
        "aim it with rotation in radians), SPOT (cone of light, spot_angle in degrees), "
        "AREA (soft panel, size = width). color is [r,g,b] 0-1, e.g. warm fire [1.0,0.5,0.15], "
        "cool moonlight [0.5,0.6,1.0]. Use several coloured lights for mood (warm key + "
        "coloured rim lights)."
    )
    permission = Permission.SAFE_WRITE
    input_model = CreateLightInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: CreateLightInput) -> ToolResult:
        light_obj = self._bridge.create_light(
            name=validated_input.name,
            light_type=validated_input.light_type,
            location=validated_input.location,
            rotation=validated_input.rotation,
            color=validated_input.color,
            energy=validated_input.energy,
            size=validated_input.size,
            spot_angle=validated_input.spot_angle,
        )

        return ToolResult.ok({
            "name": light_obj.name,
            "light_type": validated_input.light_type,
            "location": list(light_obj.location),
            "color": validated_input.color,
            "energy": validated_input.energy,
        })


class SetWorldTool(Tool):
    name = "world.set"
    description = (
        "Sets the world/sky background: color [r,g,b] 0-1 and strength (ambient brightness, "
        "0 = pitch black, ~0.05-0.3 = night, 1 = daylight). Use a dark blue/purple colour with "
        "low strength for a night scene, a light blue with strength ~1 for a day sky."
    )
    permission = Permission.SAFE_WRITE
    input_model = SetWorldInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: SetWorldInput) -> ToolResult:
        world = self._bridge.set_world(
            color=validated_input.color,
            strength=validated_input.strength,
        )

        if world is None:
            return ToolResult.fail("Could not set the world background.")

        return ToolResult.ok(world)
