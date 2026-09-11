from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.skills.builtins.product_showcase import ProductShowcaseSkill
from blender_ai_agent.tools.camera_tools import CreateCameraTool
from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool
from blender_ai_agent.tools.object_tools import CreateObjectTool, DeleteObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.agent.tool_caller import ToolCaller
from .fakes import FakeBridge


def build_registry():
    bridge = FakeBridge()
    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))
    registry.register(CreateCameraTool(bridge))
    registry.register(DeleteObjectTool(bridge))
    return registry


class TestSkillPermissions(unittest.TestCase):

    def test_required_permissions_lists_tools(self):
        registry = build_registry()
        tool_caller = ToolCaller(registry)
        skill = ProductShowcaseSkill(tool_caller)

        permissions = skill.required_permissions(registry)

        self.assertIn("object.create", permissions)
        self.assertIn("camera.create", permissions)

    def test_product_showcase_has_no_destructive_operations(self):
        registry = build_registry()
        tool_caller = ToolCaller(registry)
        skill = ProductShowcaseSkill(tool_caller)

        self.assertFalse(skill.has_destructive_operations(registry))

    def test_default_required_permissions_is_empty(self):
        from blender_ai_agent.skills.base import Skill, SkillResult

        class SimpleSkill(Skill):
            name = "simple"

            def execute(self, context):
                return SkillResult.ok()

        registry = build_registry()
        skill = SimpleSkill(tool_caller=None)

        self.assertEqual(skill.required_permissions(registry), [])


if __name__ == "__main__":
    unittest.main()