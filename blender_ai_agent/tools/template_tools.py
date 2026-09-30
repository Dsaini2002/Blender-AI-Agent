"""
Template Tools
=============
Hinglish: Ye tool LLM se coordinate-guessing hatata hai. Har baar
"create a spiderman/human" prompt se model 26 parts ke coordinates
khud generate karta tha - kabhi galat scale, kabhi missing joint,
kabhi gap. Ab ek FIXED spec file (templates/<name>.json) se exact
wahi structure deterministically banta hai - model sirf prefix aur
color choose karta hai, geometry hardcoded hai.
"""

import json
import os

from .base import Permission, Tool, ToolResult
from .models import BuildTemplateInput

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")


class BuildTemplateTool(Tool):
    name = "template.build"
    description = (
        "Builds a complete, pre-defined body/object structure (e.g. 'humanoid' - a full "
        "26-part character with feet, knee-jointed legs, hips, torso, elbow-jointed arms, "
        "hands, neck, head, eyes) from a fixed template file, instead of creating each part "
        "one-by-one with guessed coordinates. Use this whenever the user asks for a "
        "person/character/robot/humanoid - it is far more reliable than manually placing "
        "26 parts (no missing joints, no floating parts, no gaps). Pass `prefix` (e.g. "
        "'spidey_') to name all parts, and optionally `colors` (e.g. "
        '{"primary": [0.8, 0.1, 0.1, 1.0], "secondary": [0.1, 0.2, 0.8, 1.0]}) to override '
        "the default red/blue scheme. After calling this, you can still add a few extra "
        "themed details on top (visor, spider-web pattern) using the normal tools - you "
        "do not need to build the base body by hand."
    )
    permission = Permission.SAFE_WRITE
    input_model = BuildTemplateInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: BuildTemplateInput) -> ToolResult:
        template_path = os.path.join(_TEMPLATES_DIR, f"{validated_input.template_name}.json")
        try:
            with open(template_path, "r", encoding="utf-8") as f:
                template = json.load(f)
        except FileNotFoundError:
            available = [
                fname[:-5] for fname in os.listdir(_TEMPLATES_DIR)
                if fname.endswith(".json")
            ] if os.path.isdir(_TEMPLATES_DIR) else []
            return ToolResult.fail(
                f"No template named '{validated_input.template_name}'. "
                f"Available: {', '.join(available) or '(none found)'}"
            )
        except (OSError, json.JSONDecodeError) as exc:
            return ToolResult.fail(f"Could not read template '{validated_input.template_name}': {exc}")

        prefix = validated_input.prefix
        colors = validated_input.colors or {}
        material_groups = template.get("material_groups", {})

        created_materials = {}
        for group, spec in material_groups.items():
            color = colors.get(group, spec.get("default_color", [0.5, 0.5, 0.5, 1.0]))
            material_name = f"{prefix}mat_{group}"
            self._bridge.create_material(name=material_name, color=color)
            created_materials[group] = material_name

        created_objects = []
        for part in template.get("parts", []):
            if part.get("optional") and not validated_input.include_optional_parts:
                continue

            part_name = part["name"].replace("{p}", prefix)
            self._bridge.create_object(
                name=part_name,
                object_type=part.get("object_type", "MESH"),
                primitive=part.get("primitive", "CUBE"),
                location=part.get("location"),
            )
            if part.get("scale") is not None:
                self._bridge.transform_object(part_name, scale=part["scale"])

            group = part.get("material_group")
            if group and group in created_materials:
                self._bridge.assign_material(part_name, created_materials[group])

            bevel = part.get("bevel")
            if bevel:
                self._bridge.add_modifier(part_name, "Bevel", "BEVEL")
                self._bridge.configure_modifier(part_name, "Bevel", bevel)

            # Hinglish: Kuch parts (dimples, eye-socket recess) khud
            # dikhna nahi chahte - sirf ek TARGET part se unka shape
            # BOOLEAN-DIFFERENCE se "kaat" diya jaata hai (real indentation,
            # sirf color se fake nahi), phir cutter chhupa diya jaata hai.
            cut_target = part.get("boolean_cut_target")
            if cut_target:
                target_name = cut_target.replace("{p}", prefix)
                modifier_name = f"Cut_{part_name}"
                self._bridge.add_modifier(target_name, modifier_name, "BOOLEAN")
                self._bridge.configure_modifier(
                    target_name, modifier_name, {"object": part_name, "operation": "DIFFERENCE"}
                )
                if part.get("hide", True):
                    self._bridge.set_object_visibility(part_name, True)

            created_objects.append(part_name)

        return ToolResult.ok({
            "template": validated_input.template_name,
            "created_objects": created_objects,
            "part_count": len(created_objects),
        })