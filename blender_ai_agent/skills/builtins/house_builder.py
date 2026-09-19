"""
HouseBuilderSkill
====================
Hinglish: ProductShowcaseSkill jaisa hi pattern (Skill = multiple
Tools ka composition), lekin iska kaam hai: user "house"/"ghar" bole
to poora ghar ban jaye — walls, roof, door, 2 windows — sabme color.

    house_builder
        1. object.create    (Walls  — CUBE)
        2. object.transform (Walls ko size dena)
        3. material.create + material.assign  (Walls color)
        4. object.create    (Roof   — CONE)
        5. object.transform (Roof ko position/size dena)
        6. material.create + material.assign  (Roof color)
        7. object.create    (Door   — CUBE, chhota)
        8. object.transform
        9. material.create + material.assign  (Door color)
       10-12. Window Left  (CUBE + transform + material)
       13-15. Window Right (CUBE + transform + material)

Har part ka apna naam hota hai (`{house_name}_Walls`, `_Roof`, etc.)
taaki ek scene mein multiple houses bhi ban sakein bina naam clash ke.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..base import Skill, SkillResult


class HouseBuildError(Exception):
    """Hinglish: Beech mein koi step fail ho jaye to poora build rokne ke liye."""

    def __init__(self, message: str, steps_completed: List[str]):
        super().__init__(message)
        self.steps_completed = steps_completed


@dataclass
class HouseBuilderParams:
    house_name: str = "House"
    wall_color: List[float] = None
    roof_color: List[float] = None
    door_color: List[float] = None
    window_color: List[float] = None
    location: List[float] = None

    def __post_init__(self):
        # Hinglish: Defaults ek normal ghar jaisa dikhte hain agar
        # user ne koi color specify nahi kiya — cream walls, red
        # roof, brown door, light-blue (glass-jaisi) windows.
        if self.wall_color is None:
            self.wall_color = [0.85, 0.78, 0.65, 1.0]
        if self.roof_color is None:
            self.roof_color = [0.55, 0.15, 0.1, 1.0]
        if self.door_color is None:
            self.door_color = [0.35, 0.2, 0.1, 1.0]
        if self.window_color is None:
            self.window_color = [0.6, 0.8, 0.9, 1.0]
        if self.location is None:
            self.location = [0.0, 0.0, 0.0]


class HouseBuilderSkill(Skill):
    name = "house_builder"
    description = (
        "Builds a complete, coloured house (walls, roof, door, two windows) "
        "from a single request — e.g. 'make a house' or 'build a colourful home'."
    )

    # Hinglish: Default keyword-match (Skill.can_handle) sirf naam ke
    # words ("house", "builder") dekhta hai jo bahut narrow hai.
    # Yahan explicit synonyms match karte hain taaki "make a house",
    # "build a home", "ghar banao" sab match ho jayein.
    _TRIGGER_WORDS = ("house", "home", "cottage", "ghar", "bungalow")

    def can_handle(self, task: str) -> float:
        task_lower = task.lower()
        return 1.0 if any(word in task_lower for word in self._TRIGGER_WORDS) else 0.0

    def execute(self, context: Dict[str, Any]) -> SkillResult:
        """Hinglish: Public entrypoint — asli kaam _build() karta hai,
        yahan sirf error ko SkillResult.fail() mein convert karte hain
        taaki caller ko kabhi raw exception na dikhe (Skill contract)."""
        try:
            return self._build(context)
        except HouseBuildError as exc:
            return SkillResult.fail(str(exc), exc.steps_completed)

    def _build(self, context: Dict[str, Any]) -> SkillResult:
        params = HouseBuilderParams(
            house_name=context.get("house_name", "House"),
            wall_color=context.get("wall_color"),
            roof_color=context.get("roof_color"),
            door_color=context.get("door_color"),
            window_color=context.get("window_color"),
            location=context.get("location"),
        )

        steps_completed: List[str] = []
        ox, oy, oz = params.location

        # ---- 1) Walls (CUBE, scaled wide+tall) ----
        walls_name = f"{params.house_name}_Walls"
        self._create(walls_name, "CUBE", [ox, oy, oz + 1.0], steps_completed)
        self._transform(walls_name, scale=[2.0, 1.5, 1.0], steps_completed=steps_completed)
        self._paint(walls_name, params.wall_color, steps_completed)

        # ---- 2) Roof (CONE, sits on top, scaled) ----
        roof_name = f"{params.house_name}_Roof"
        self._create(roof_name, "CONE", [ox, oy, oz + 2.35], steps_completed)
        self._transform(roof_name, scale=[1.6, 1.6, 1.2], steps_completed=steps_completed)
        self._paint(roof_name, params.roof_color, steps_completed)

        # ---- 3) Door (small CUBE, front-centre) ----
        door_name = f"{params.house_name}_Door"
        self._create(door_name, "CUBE", [ox, oy - 1.51, oz + 0.5], steps_completed)
        self._transform(door_name, scale=[0.4, 0.05, 0.6], steps_completed=steps_completed)
        self._paint(door_name, params.door_color, steps_completed)

        # ---- 4) Window — Left ----
        win_l_name = f"{params.house_name}_Window_Left"
        self._create(win_l_name, "CUBE", [ox - 1.1, oy - 1.51, oz + 1.1], steps_completed)
        self._transform(win_l_name, scale=[0.3, 0.05, 0.3], steps_completed=steps_completed)
        self._paint(win_l_name, params.window_color, steps_completed)

        # ---- 5) Window — Right ----
        win_r_name = f"{params.house_name}_Window_Right"
        self._create(win_r_name, "CUBE", [ox + 1.1, oy - 1.51, oz + 1.1], steps_completed)
        self._transform(win_r_name, scale=[0.3, 0.05, 0.3], steps_completed=steps_completed)
        self._paint(win_r_name, params.window_color, steps_completed)

        return SkillResult.ok(
            data={
                "house_name": params.house_name,
                "parts": [walls_name, roof_name, door_name, win_l_name, win_r_name],
            },
            steps_completed=steps_completed,
        )

    # ------------------------------------------------------------------
    # Internal helpers — har ek "object.create / object.transform /
    # material.create+assign" sequence isi pattern se guzarta hai,
    # isliye chhote helpers poora method-chain repeat hone se bachate hain.
    # ------------------------------------------------------------------

    def _create(self, name: str, primitive: str, location: List[float], steps_completed: List[str]) -> None:
        result = self._tool_caller.call(self._make_call("object.create", {
            "name": name, "primitive": primitive, "location": location,
        }))
        if not result.success:
            raise HouseBuildError(f"Failed at object.create({name}): {result.error}", steps_completed)
        steps_completed.append(f"object.create:{name}")

    def _transform(
        self, name: str, scale: Optional[List[float]] = None,
        rotation: Optional[List[float]] = None, *, steps_completed: List[str],
    ) -> None:
        args: Dict[str, Any] = {"name": name}
        if scale is not None:
            args["scale"] = scale
        if rotation is not None:
            args["rotation"] = rotation
        result = self._tool_caller.call(self._make_call("object.transform", args))
        if not result.success:
            raise HouseBuildError(f"Failed at object.transform({name}): {result.error}", steps_completed)
        steps_completed.append(f"object.transform:{name}")

    def _paint(self, object_name: str, color: List[float], steps_completed: List[str]) -> None:
        material_name = f"{object_name}_Material"

        result = self._tool_caller.call(self._make_call("material.create", {
            "name": material_name, "color": color,
        }))
        if not result.success:
            raise HouseBuildError(f"Failed at material.create({material_name}): {result.error}", steps_completed)
        steps_completed.append(f"material.create:{material_name}")

        result = self._tool_caller.call(self._make_call("material.assign", {
            "object_name": object_name, "material_name": material_name,
        }))
        if not result.success:
            raise HouseBuildError(f"Failed at material.assign({object_name}): {result.error}", steps_completed)
        steps_completed.append(f"material.assign:{object_name}")

    def required_permissions(self, tool_registry) -> list:
        return ["object.create", "object.transform", "material.create", "material.assign"]

    @staticmethod
    def _make_call(tool_name: str, arguments: Dict[str, Any]):
        from ...agent.models import ToolCall
        return ToolCall(tool_name=tool_name, arguments=arguments)