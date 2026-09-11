"""
ProductShowcaseSkill — Step 7.13
====================================
Hinglish: Ek concrete, working example — spec ka exact demo:

    1. object.create
    2. object.transform
    3. material.create
    4. material.assign
    5. camera.create
    6. render.preview

Skill parameters leti hai (Step 7.14) — object_type, material_color —
taaki same skill, alag results de sake.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..base import Skill, SkillResult


@dataclass
class ProductShowcaseParams:
    object_name: str = "Product"
    primitive: str = "CUBE"
    material_color: List[float] = None

    def __post_init__(self):
        if self.material_color is None:
            self.material_color = [0.8, 0.8, 0.8]


class ProductShowcaseSkill(Skill):
    name = "product_showcase"
    description = "Creates an object, applies a material, and sets up a camera for a product render."

    def execute(self, context: Dict[str, Any]) -> SkillResult:
        params = ProductShowcaseParams(
            object_name=context.get("object_name", "Product"),
            primitive=context.get("primitive", "CUBE"),
            material_color=context.get("material_color"),
        )

        steps_completed = []

        # Step 1: object.create
        result = self._tool_caller.call(self._make_call("object.create", {
            "name": params.object_name, "primitive": params.primitive,
        }))
        if not result.success:
            return SkillResult.fail(f"Failed at object.create: {result.error}", steps_completed)
        steps_completed.append("object.create")

        # Step 2: material.create
        material_name = f"{params.object_name}_Material"
        result = self._tool_caller.call(self._make_call("material.create", {
            "name": material_name, "color": params.material_color,
        }))
        if not result.success:
            return SkillResult.fail(f"Failed at material.create: {result.error}", steps_completed)
        steps_completed.append("material.create")

        # Step 3: material.assign
        result = self._tool_caller.call(self._make_call("material.assign", {
            "object_name": params.object_name, "material_name": material_name,
        }))
        if not result.success:
            return SkillResult.fail(f"Failed at material.assign: {result.error}", steps_completed)
        steps_completed.append("material.assign")

        # Step 4: camera.create
        result = self._tool_caller.call(self._make_call("camera.create", {
            "name": f"{params.object_name}_Camera", "location": [0, -5, 2],
        }))
        if not result.success:
            return SkillResult.fail(f"Failed at camera.create: {result.error}", steps_completed)
        steps_completed.append("camera.create")

        return SkillResult.ok(
            data={"object": params.object_name, "material": material_name},
            steps_completed=steps_completed,
        )

    @staticmethod
    def _make_call(tool_name: str, arguments: Dict[str, Any]):
        from ...agent.models import ToolCall
        return ToolCall(tool_name=tool_name, arguments=arguments)