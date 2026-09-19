from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.skills.builtins.house_builder import HouseBuilderSkill
from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool
from blender_ai_agent.tools.object_tools import CreateObjectTool, TransformObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.agent.tool_caller import ToolCaller
from .fakes import FakeBridge


def build_skill():
    bridge = FakeBridge()
    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(TransformObjectTool(bridge))
    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))

    tool_caller = ToolCaller(registry)
    return HouseBuilderSkill(tool_caller), bridge


class TestHouseBuilderSkill(unittest.TestCase):

    def test_full_house_is_built_with_all_five_parts(self):
        skill, bridge = build_skill()

        result = skill.execute({"house_name": "MyHouse"})

        self.assertTrue(result.success)
        for suffix in ("Walls", "Roof", "Door", "Window_Left", "Window_Right"):
            self.assertIsNotNone(bridge.get_object(f"MyHouse_{suffix}"))

    def test_every_part_gets_its_own_material(self):
        skill, bridge = build_skill()

        result = skill.execute({"house_name": "Cottage"})

        self.assertTrue(result.success)
        for suffix in ("Walls", "Roof", "Door", "Window_Left", "Window_Right"):
            material = bridge.get_material(f"Cottage_{suffix}_Material")
            self.assertIsNotNone(material)

    def test_custom_colors_are_applied(self):
        skill, bridge = build_skill()

        result = skill.execute({
            "house_name": "Villa",
            "roof_color": [1.0, 0.0, 0.0, 1.0],
            "wall_color": [0.0, 0.0, 1.0, 1.0],
        })

        self.assertTrue(result.success)
        roof_material = bridge.get_material("Villa_Roof_Material")
        wall_material = bridge.get_material("Villa_Walls_Material")
        self.assertEqual(roof_material.color, [1.0, 0.0, 0.0, 1.0])
        self.assertEqual(wall_material.color, [0.0, 0.0, 1.0, 1.0])

    def test_default_colors_used_when_none_given(self):
        skill, bridge = build_skill()

        result = skill.execute({})

        self.assertTrue(result.success)
        self.assertIsNotNone(bridge.get_object("House_Walls"))

    def test_can_handle_matches_house_related_phrases(self):
        skill, _ = build_skill()

        self.assertEqual(skill.can_handle("make a house"), 1.0)
        self.assertEqual(skill.can_handle("build a colourful home please"), 1.0)
        self.assertEqual(skill.can_handle("ghar banao"), 1.0)
        self.assertEqual(skill.can_handle("create a spinning cube"), 0.0)

    def test_stops_and_reports_partial_progress_on_failure(self):
        """Hinglish: Agar material.assign registered hi na ho, skill
        wahi tak ke steps report kare, poora crash na ho."""
        bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(CreateObjectTool(bridge))
        registry.register(TransformObjectTool(bridge))
        registry.register(CreateMaterialTool(bridge))
        # material.assign intentionally NOT registered

        tool_caller = ToolCaller(registry)
        skill = HouseBuilderSkill(tool_caller)

        result = skill.execute({"house_name": "Broken"})

        self.assertFalse(result.success)
        self.assertIn("object.create:Broken_Walls", result.steps_completed)
        self.assertIn("material.create:Broken_Walls_Material", result.steps_completed)
        self.assertNotIn("material.assign:Broken_Walls", result.steps_completed)


if __name__ == "__main__":
    unittest.main()