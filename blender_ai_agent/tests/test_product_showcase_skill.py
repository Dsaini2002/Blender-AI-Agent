from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.skills.builtins.product_showcase import ProductShowcaseSkill
from blender_ai_agent.tools.camera_tools import CreateCameraTool
from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool
from blender_ai_agent.tools.object_tools import CreateObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.agent.tool_caller import ToolCaller
from .fakes import FakeBridge


def build_skill():
    bridge = FakeBridge()
    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))
    registry.register(CreateCameraTool(bridge))

    tool_caller = ToolCaller(registry)
    return ProductShowcaseSkill(tool_caller), bridge


class TestProductShowcaseSkill(unittest.TestCase):

    def test_full_workflow_succeeds(self):
        skill, bridge = build_skill()

        result = skill.execute({"object_name": "Vase", "primitive": "CUBE"})

        self.assertTrue(result.success)
        self.assertEqual(result.steps_completed, [
            "object.create", "material.create", "material.assign", "camera.create"
        ])
        self.assertIsNotNone(bridge.get_object("Vase"))
        self.assertIsNotNone(bridge.get_object("Vase_Camera"))

    def test_default_parameters_used_when_not_provided(self):
        skill, bridge = build_skill()

        result = skill.execute({})

        self.assertTrue(result.success)
        self.assertIsNotNone(bridge.get_object("Product"))

    def test_custom_material_color_applied(self):
        skill, bridge = build_skill()

        result = skill.execute({"object_name": "Chair", "material_color": [1, 0, 0]})

        self.assertTrue(result.success)
        material = bridge.get_material("Chair_Material")
        self.assertEqual(material.color, [1, 0, 0, 1.0])

    def test_stops_and_reports_partial_progress_on_failure(self):
        """Hinglish: Agar camera.create registered hi na ho, skill wahi tak steps report kare."""
        bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(CreateObjectTool(bridge))
        registry.register(CreateMaterialTool(bridge))
        registry.register(AssignMaterialTool(bridge))
        # camera.create intentionally NOT registered

        tool_caller = ToolCaller(registry)
        skill = ProductShowcaseSkill(tool_caller)

        result = skill.execute({"object_name": "Broken"})

        self.assertFalse(result.success)
        self.assertEqual(result.steps_completed, ["object.create", "material.create", "material.assign"])


if __name__ == "__main__":
    unittest.main()