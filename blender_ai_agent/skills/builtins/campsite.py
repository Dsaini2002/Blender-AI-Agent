"""
CampsiteSkill
==============
Hinglish: HouseBuilderSkill jaisa hi pattern (Skill = multiple Tools ka
composition), lekin ye ek POORA scene banata hai — user "campsite" /
"campfire" / "tent" bole to ek low-poly night camping scene ban jaata hai:

    campsite
        1. Ground              (PLANE)
        2. Tent                (2 slanted CUBE panels = A-frame)
        3. Campfire            (stone ring + 2 logs + 2 emissive flame CONEs)
        4. Pine trees          (trunk + 3 stacked CONEs, back arc mein)
        5. Log, stool, rocks, mushrooms
        6. Moon + clouds       (emissive)
        7. Lighting            (fire point light, moonlight sun, coloured rim lights)
        8. World background    (dark night colour)
        9. Camera              (scene ki taraf aim kiya hua)

Design notes:
  - Shared materials: ek colour ka material ek baar banta hai aur bahut se
    objects par assign hota hai (har tree ke liye alag material nahi) — tool
    calls kam, aur scene mein colour-consistency.
  - Har step ka asli naam (Blender .001 suffix laga sakta hai) tool result se
    liya jaata hai, isliye dobara run karne par bhi galat object edit nahi hota.
  - Placement `seed` se deterministic hai — same seed = same scene.
"""

import math
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..base import Skill, SkillResult


class CampsiteBuildError(Exception):
    """Hinglish: Beech mein koi step fail ho jaye to poora build rokne ke liye."""

    def __init__(self, message: str, steps_completed: List[str]):
        super().__init__(message)
        self.steps_completed = steps_completed


@dataclass
class CampsiteParams:
    camp_name: str = "Campsite"
    location: List[float] = None
    tree_count: int = 6
    rock_count: int = 4
    seed: int = 7
    night: bool = True
    add_camera: bool = True
    clear_defaults: bool = False

    def __post_init__(self):
        if not self.camp_name or not isinstance(self.camp_name, str):
            raise ValueError("camp_name must be a non-empty string")
        if self.location is None:
            self.location = [0.0, 0.0, 0.0]
        if len(self.location) != 3:
            raise ValueError("location must have exactly 3 values [x, y, z]")
        if not isinstance(self.tree_count, int) or not (0 <= self.tree_count <= 12):
            raise ValueError("tree_count must be an integer between 0 and 12")
        if not isinstance(self.rock_count, int) or not (0 <= self.rock_count <= 10):
            raise ValueError("rock_count must be an integer between 0 and 10")
        if not isinstance(self.seed, int):
            raise ValueError("seed must be an integer")
        if not isinstance(self.clear_defaults, bool):
            raise ValueError("clear_defaults must be true or false")


# Hinglish: Layout (campfire = origin). Har tuple = (x, y) ground position.
_TENT_POS = (-3.2, 1.8)
_TENT_YAW = math.radians(20)
_LOG_POS = (3.8, 1.2)
_STOOL_POS = (-2.2, -2.2)
_MUSHROOM_POS = [(2.6, -1.6), (3.05, -1.3)]

# (x, y, clearance radius) — rocks/trees in zones se door rakhe jaate hain
_OCCUPIED = [
    (0.0, 0.0, 1.4),
    (_TENT_POS[0], _TENT_POS[1], 2.0),
    (_LOG_POS[0], _LOG_POS[1], 1.8),
    (_STOOL_POS[0], _STOOL_POS[1], 0.9),
    (_MUSHROOM_POS[0][0], _MUSHROOM_POS[0][1], 0.7),
]


class CampsiteSkill(Skill):
    name = "campsite"
    description = (
        "Builds a complete low-poly camping scene — tent, glowing campfire, pine trees, log, "
        "stool, rocks, mushrooms, moon, clouds, coloured lighting, night sky and camera — "
        "from a single request, e.g. 'make a campsite' or 'create a night camping scene'."
    )

    _TRIGGER = re.compile(r"\b(camp|camps|camping|campsite|campfire|bonfire|tent)\b|camp\s+(site|fire)")

    def can_handle(self, task: str) -> float:
        return 1.0 if self._TRIGGER.search(task.lower()) else 0.0

    def execute(self, context: Dict[str, Any]) -> SkillResult:
        """Hinglish: Public entrypoint — kisi bhi build/validation error ko
        SkillResult.fail() mein badalta hai (Skill contract: raw exception nahi)."""
        try:
            return self._build(context)
        except CampsiteBuildError as exc:
            return SkillResult.fail(str(exc), exc.steps_completed)
        except ValueError as exc:
            return SkillResult.fail(f"Invalid campsite options: {exc}", [])

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def _build(self, context: Dict[str, Any]) -> SkillResult:
        params = CampsiteParams(
            camp_name=context.get("camp_name", "Campsite"),
            location=context.get("location"),
            tree_count=context.get("tree_count", 6),
            rock_count=context.get("rock_count", 4),
            seed=context.get("seed", 7),
            night=context.get("night", True),
            add_camera=context.get("add_camera", True),
            clear_defaults=context.get("clear_defaults", False),
        )

        self._p = params
        self._steps: List[str] = []
        self._parts: Dict[str, List[str]] = {}
        self._mats: Dict[str, str] = {}
        self._rng = random.Random(params.seed)
        self._occupied: List[Tuple[float, float, float]] = list(_OCCUPIED)

        # Hinglish: Build SE PEHLE scene dekho — Blender ke startup "Cube"/"Light"
        # campfire ke upar baithe hote hain. Chupchaap delete nahi karte (destructive),
        # lekin ignore bhi nahi karte: ya to user ke kehne par hataate hain,
        # ya result mein note karke poochte hain.
        leftovers = self._find_default_leftovers()
        notes: List[str] = []
        if leftovers and params.clear_defaults:
            for item in leftovers:
                self._call("object.delete", {"name": item["name"]})
                self._steps.append(f"object.delete:{item['name']}")
                notes.append(f"Deleted the leftover default '{item['name']}' as requested.")
        elif leftovers:
            notes.extend(self._leftover_questions(leftovers))

        self._build_ground()
        self._build_tent()
        self._build_campfire()
        self._build_props()
        self._build_rocks()
        self._build_trees()
        self._build_sky_objects()
        self._build_lighting()
        camera_name = self._build_camera() if params.add_camera else None

        data = {
            "camp_name": params.camp_name,
            "parts": self._parts,
            "object_count": sum(len(v) for v in self._parts.values()),
            "camera": camera_name,
            "night": params.night,
            "leftover_defaults": [i["name"] for i in leftovers] if not params.clear_defaults else [],
        }
        if notes:
            data["notes"] = notes
        return SkillResult.ok(data=data, steps_completed=self._steps)

    # -------------------------- scene parts ---------------------------
    def _build_ground(self) -> None:
        self._obj("ground", "Ground", "PLANE", (0.0, 0.0, 0.0), scale=(14.0, 14.0, 1.0),
                  material=self._mat("Ground", [0.28, 0.12, 0.14, 1.0]))

    def _build_tent(self) -> None:
        # A-frame: base half-width w, height h. Panels CUBE (2m default) -> scale = size/2.
        w, h, half_len = 1.0, 1.1, 1.2
        slant = math.hypot(w, h)
        tilt = math.atan2(w, h)
        panel_scale = (half_len, 0.03, slant / 2)

        mat_a = self._mat("TentBlue", [0.3, 0.5, 0.7, 1.0])
        mat_b = self._mat("TentGreen", [0.3, 0.7, 0.4, 1.0])

        for suffix, side, mat in (("PanelLeft", -1, mat_a), ("PanelRight", 1, mat_b)):
            local = (0.0, side * w / 2, h / 2)
            x, y = self._rot_xy(local[0], local[1], _TENT_YAW)
            self._obj(
                "tent", suffix, "CUBE",
                (_TENT_POS[0] + x, _TENT_POS[1] + y, local[2]),
                scale=panel_scale,
                rotation=(side * tilt, 0.0, _TENT_YAW),
                material=mat,
            )

    def _build_campfire(self) -> None:
        stone_mat = self._mat("Stone", [0.45, 0.42, 0.5, 1.0])
        for i in range(8):
            angle = i * (2 * math.pi / 8)
            self._obj("campfire", f"Stone{i + 1}", "ICOSPHERE",
                      (0.75 * math.cos(angle), 0.75 * math.sin(angle), 0.08),
                      scale=(0.16, 0.16, 0.1), material=stone_mat)

        wood_mat = self._mat("Wood", [0.25, 0.1, 0.06, 1.0])
        for i, yaw in enumerate((0.8, -0.8)):
            self._obj("campfire", f"FireLog{i + 1}", "CYLINDER", (0.0, 0.0, 0.12),
                      scale=(0.08, 0.08, 0.45), rotation=(0.0, math.pi / 2, yaw), material=wood_mat)

        flame_outer = self._mat("FlameOuter", [1.0, 0.35, 0.05, 1.0],
                                emission=([1.0, 0.35, 0.05], 10.0))
        flame_inner = self._mat("FlameInner", [1.0, 0.85, 0.2, 1.0],
                                emission=([1.0, 0.85, 0.2], 15.0))
        self._obj("campfire", "FlameOuter", "CONE", (0.0, 0.0, 0.65),
                  scale=(0.32, 0.32, 0.55), material=flame_outer)
        self._obj("campfire", "FlameInner", "CONE", (0.0, 0.0, 0.45),
                  scale=(0.18, 0.18, 0.35), material=flame_inner)

    def _build_props(self) -> None:
        # Log (laying down, long axis along X, yawed)
        self._obj("props", "Log", "CYLINDER", (_LOG_POS[0], _LOG_POS[1], 0.25),
                  scale=(0.25, 0.25, 1.4), rotation=(0.0, math.pi / 2, math.radians(-15)),
                  material=self._mat("LogWood", [0.55, 0.18, 0.12, 1.0]))

        # Folding stool
        seat_mat = self._mat("StoolSeat", [0.2, 0.5, 0.8, 1.0])
        leg_mat = self._mat("StoolLeg", [0.7, 0.72, 0.8, 1.0])
        sx, sy = _STOOL_POS
        self._obj("props", "StoolSeat", "CUBE", (sx, sy, 0.55), scale=(0.32, 0.32, 0.03), material=seat_mat)
        for i, (dx, dy) in enumerate(((1, 1), (1, -1), (-1, 1), (-1, -1))):
            self._obj("props", f"StoolLeg{i + 1}", "CYLINDER",
                      (sx + dx * 0.26, sy + dy * 0.26, 0.27),
                      scale=(0.025, 0.025, 0.27), material=leg_mat)

        # Mushrooms
        stem_mat = self._mat("MushroomStem", [0.9, 0.85, 0.75, 1.0])
        cap_mat = self._mat("MushroomCap", [0.8, 0.1, 0.12, 1.0])
        for i, (mx, my) in enumerate(_MUSHROOM_POS):
            self._obj("props", f"Mushroom{i + 1}_Stem", "CYLINDER", (mx, my, 0.12),
                      scale=(0.04, 0.04, 0.12), material=stem_mat)
            self._obj("props", f"Mushroom{i + 1}_Cap", "SPHERE", (mx, my, 0.26),
                      scale=(0.13, 0.13, 0.08), material=cap_mat)

    def _build_rocks(self) -> None:
        rock_mat = self._mat("Rock", [0.32, 0.3, 0.5, 1.0])
        placed = 0
        attempts = 0
        while placed < self._p.rock_count and attempts < 80:
            attempts += 1
            angle = self._rng.uniform(0, 2 * math.pi)
            radius = self._rng.uniform(3.0, 6.5)
            x, y = radius * math.cos(angle), radius * math.sin(angle)
            if self._is_blocked(x, y, 0.8):
                continue
            sx = self._rng.uniform(0.4, 0.9)
            sy = self._rng.uniform(0.35, 0.7)
            sz = self._rng.uniform(0.25, 0.5)
            self._obj("rocks", f"Rock{placed + 1}", "ICOSPHERE", (x, y, sz * 0.7),
                      scale=(sx, sy, sz), rotation=(0.0, 0.0, self._rng.uniform(0, math.pi)),
                      material=rock_mat)
            self._occupied.append((x, y, max(sx, sy)))
            placed += 1

    def _build_trees(self) -> None:
        n = self._p.tree_count
        trunk_mat = self._mat("Trunk", [0.25, 0.1, 0.08, 1.0])
        leaf_mat = self._mat("PineLeaves", [0.12, 0.3, 0.28, 1.0])

        for i in range(n):
            # Back arc (y > 0), evenly spaced + jitter, kept away from other props.
            for _ in range(20):
                angle = math.radians(25 + 130 * (i + 0.5) / n + self._rng.uniform(-6, 6))
                radius = self._rng.uniform(6.5, 9.5)
                x, y = radius * math.cos(angle), radius * math.sin(angle)
                if not self._is_blocked(x, y, 1.0):
                    break
            s = self._rng.uniform(0.9, 1.4)
            tag = f"Tree{i + 1}"

            self._obj("trees", f"{tag}_Trunk", "CYLINDER", (x, y, 0.5 * s),
                      scale=(0.15 * s, 0.15 * s, 0.5 * s), material=trunk_mat)
            # 3 stacked cone tiers; cone default radius 1, height 2 -> scale = (r, r, height/2)
            for tier, (radius_k, base_k) in enumerate(((1.3, 0.9), (1.0, 1.9), (0.7, 2.8))):
                self._obj("trees", f"{tag}_Tier{tier + 1}", "CONE",
                          (x, y, (base_k + 0.75) * s),
                          scale=(radius_k * s, radius_k * s, 0.75 * s), material=leaf_mat)
            self._occupied.append((x, y, 1.0 * s))

    def _build_sky_objects(self) -> None:
        if self._p.night:
            moon_mat = self._mat("Moon", [1.0, 0.95, 0.7, 1.0], emission=([1.0, 0.95, 0.7], 6.0))
            self._obj("sky", "Moon", "SPHERE", (-5.0, 16.0, 11.0), scale=(1.4, 1.4, 1.4), material=moon_mat)
            cloud_mat = self._mat("Cloud", [0.55, 0.3, 0.7, 1.0], emission=([0.45, 0.25, 0.6], 0.5))
        else:
            cloud_mat = self._mat("Cloud", [0.95, 0.95, 1.0, 1.0])

        for c in range(3):
            cx = self._rng.uniform(-12, 12)
            cy = self._rng.uniform(10, 18)
            cz = self._rng.uniform(7, 10)
            for j, (dx, dz, scale) in enumerate((
                (-1.1, 0.0, (1.3, 0.9, 0.6)),
                (0.0, 0.3, (1.6, 1.1, 0.8)),
                (1.1, 0.0, (1.3, 0.9, 0.6)),
            )):
                self._obj("sky", f"Cloud{c + 1}_Puff{j + 1}", "SPHERE", (cx + dx, cy, cz + dz),
                          scale=scale, material=cloud_mat)

    def _build_lighting(self) -> None:
        ox, oy, oz = self._p.location

        self._light("FireLight", "POINT", (ox, oy, oz + 0.9), color=(1.0, 0.5, 0.15),
                    energy=800.0, size=0.3)

        if self._p.night:
            self._light("MoonLight", "SUN", (ox, oy, oz + 10.0), color=(0.5, 0.6, 1.0), energy=0.8,
                        rotation=(math.radians(-50), 0.0, math.radians(30)))
            self._light("RimGreen", "POINT", (ox + 7, oy + 4, oz + 3), color=(0.2, 1.0, 0.45),
                        energy=400.0, size=0.5)
            self._light("RimPurple", "POINT", (ox - 7, oy + 3, oz + 3), color=(0.65, 0.3, 1.0),
                        energy=400.0, size=0.5)
            self._world([0.03, 0.03, 0.09], 0.35)
        else:
            self._light("Sun", "SUN", (ox, oy, oz + 10.0), color=(1.0, 0.95, 0.85), energy=3.5,
                        rotation=(math.radians(45), 0.0, math.radians(30)))
            self._world([0.45, 0.65, 0.95], 1.0)

    def _build_camera(self) -> str:
        ox, oy, oz = self._p.location
        # Camera looks down -Z; pitch so it aims at ~(0,0,1.5) from 12m back / 5.5m high.
        pitch = math.atan2(5.5 - 1.5, 12.0)
        rotation = [math.pi / 2 - pitch, 0.0, 0.0]

        result = self._call("camera.create", {
            "name": f"{self._p.camp_name}_Camera",
            "location": [ox, oy - 12.0, oz + 5.5],
            "rotation": rotation,
        })
        camera_name = result.data["name"]
        self._steps.append(f"camera.create:{camera_name}")
        self._call("camera.set", {"name": camera_name})
        self._steps.append(f"camera.set:{camera_name}")
        return camera_name

    # ------------------------------------------------------------------
    # Leftover default objects (startup Cube / Light)
    # ------------------------------------------------------------------
    _DEFAULT_NAME = re.compile(r"^(Cube|Light)(\.\d{3})?$")

    def _find_default_leftovers(self) -> List[Dict[str, Any]]:
        """
        Hinglish: scene.inspect se Blender ke factory-default Cube/Light dhoondhta hai.
        scene.inspect available na ho (ya fail ho) to chupchaap [] — ye sirf ek
        suggestion feature hai, isse build kabhi fail nahi hona chahiye.
        """
        from ...agent.models import ToolCall

        result = self._tool_caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        if not result.success or not isinstance(result.data, dict):
            return []

        ox, oy, _ = self._p.location
        found = []
        for obj in result.data.get("objects", []):
            name = obj.get("name", "")
            match = self._DEFAULT_NAME.match(name)
            if not match:
                continue
            kind = match.group(1)
            if (kind == "Cube" and obj.get("type") != "MESH") or (kind == "Light" and obj.get("type") != "LIGHT"):
                continue
            loc = obj.get("location") or [0.0, 0.0, 0.0]
            found.append({
                "name": name,
                "kind": kind,
                "overlaps": kind == "Cube" and math.hypot(loc[0] - ox, loc[1] - oy) < 2.5,
            })
        return found

    @staticmethod
    def _leftover_questions(leftovers: List[Dict[str, Any]]) -> List[str]:
        notes = []
        for item in leftovers:
            if item["kind"] == "Cube":
                where = " right where the campfire is" if item["overlaps"] else ""
                notes.append(
                    f"The default '{item['name']}' is still in the scene{where}. "
                    f"Want me to delete it? (say 'delete the default cube')"
                )
            else:
                notes.append(
                    f"The default '{item['name']}' is still in the scene and will brighten the night mood. "
                    f"Want me to delete it? (say 'delete the default light')"
                )
        return notes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _call(self, tool_name: str, arguments: Dict[str, Any]):
        from ...agent.models import ToolCall

        result = self._tool_caller.call(ToolCall(tool_name=tool_name, arguments=arguments))
        if not result.success:
            label = arguments.get("name", "")
            raise CampsiteBuildError(f"Failed at {tool_name}({label}): {result.error}", self._steps)
        return result

    def _obj(self, category: str, suffix: str, primitive: str, local_pos: Tuple[float, float, float],
             scale=None, rotation=None, material: Optional[str] = None) -> str:
        ox, oy, oz = self._p.location
        location = [ox + local_pos[0], oy + local_pos[1], oz + local_pos[2]]

        created = self._call("object.create", {
            "name": f"{self._p.camp_name}_{suffix}", "primitive": primitive, "location": location,
        })
        name = created.data["name"]  # actual name (Blender may add .001)
        self._steps.append(f"object.create:{name}")

        if scale is not None or rotation is not None:
            args: Dict[str, Any] = {"name": name}
            if scale is not None:
                args["scale"] = list(scale)
            if rotation is not None:
                args["rotation"] = list(rotation)
            self._call("object.transform", args)
            self._steps.append(f"object.transform:{name}")

        if material is not None:
            self._call("material.assign", {"object_name": name, "material_name": material})
            self._steps.append(f"material.assign:{name}")

        self._parts.setdefault(category, []).append(name)
        return name

    def _mat(self, key: str, color: List[float], emission: Optional[Tuple[List[float], float]] = None) -> str:
        """Shared material: ek baar banta hai, baar-baar assign hota hai."""
        if key in self._mats:
            return self._mats[key]

        created = self._call("material.create", {
            "name": f"{self._p.camp_name}_{key}_Mat", "color": color,
        })
        name = created.data["name"]
        self._steps.append(f"material.create:{name}")

        if emission is not None:
            self._call("material.modify", {
                "name": name, "emission_color": list(emission[0]), "emission_strength": emission[1],
            })
            self._steps.append(f"material.modify:{name}")

        self._mats[key] = name
        return name

    def _light(self, suffix: str, light_type: str, location, color, energy: float,
               size: float = 0.25, rotation=(0.0, 0.0, 0.0)) -> None:
        created = self._call("light.create", {
            "name": f"{self._p.camp_name}_{suffix}", "light_type": light_type,
            "location": list(location), "rotation": list(rotation),
            "color": list(color), "energy": energy, "size": size,
        })
        name = created.data["name"]
        self._steps.append(f"light.create:{name}")
        self._parts.setdefault("lights", []).append(name)

    def _world(self, color: List[float], strength: float) -> None:
        self._call("world.set", {"color": color, "strength": strength})
        self._steps.append("world.set")

    @staticmethod
    def _rot_xy(x: float, y: float, yaw: float) -> Tuple[float, float]:
        """2D rotation about Z (tent ki local position ko world mein yaw dene ke liye)."""
        return (x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw))

    def _is_blocked(self, x: float, y: float, margin: float) -> bool:
        return any(math.hypot(x - ox, y - oy) < r + margin for ox, oy, r in self._occupied)

    def required_permissions(self, tool_registry) -> list:
        return [
            "object.create", "object.transform",
            "material.create", "material.assign", "material.modify",
            "light.create", "world.set",
            "camera.create", "camera.set",
            "scene.inspect",
            "object.delete",  # only when clear_defaults=True (user asked to remove the startup Cube/Light)
        ]
