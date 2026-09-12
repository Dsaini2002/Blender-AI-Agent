from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.skills.advanced_permissions import SkillPermissionChecker
from blender_ai_agent.skills.builtins.product_showcase import ProductShowcaseSkill
from blender_ai_agent.tools.base import Permission
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


class TestSkillPermissionChecker(unittest.TestCase):

    def test_product_showcase_does_not_require_confirmation(self):
        registry = build_registry()
        tool_caller = ToolCaller(registry)
        skill = ProductShowcaseSkill(tool_caller)
        checker = SkillPermissionChecker(registry)

        self.assertFalse(checker.requires_confirmation(skill))

    def test_highest_permission_is_safe_write_for_product_showcase(self):
        registry = build_registry()
        tool_caller = ToolCaller(registry)
        skill = ProductShowcaseSkill(tool_caller)
        checker = SkillPermissionChecker(registry)

        self.assertEqual(checker.highest_permission(skill), Permission.SAFE_WRITE)

    def test_skill_with_destructive_tool_requires_confirmation(self):
        from blender_ai_agent.skills.base import Skill, SkillResult

        class CleanupSkill(Skill):
            name = "cleanup"

            def execute(self, context):
                return SkillResult.ok()

            def required_permissions(self, tool_registry):
                return ["object.delete"]

        registry = build_registry()
        skill = CleanupSkill(tool_caller=None)
        checker = SkillPermissionChecker(registry)

        self.assertTrue(checker.requires_confirmation(skill))
        self.assertEqual(checker.highest_permission(skill), Permission.DESTRUCTIVE)

    def test_no_permissions_defaults_to_read_only(self):
        from blender_ai_agent.skills.base import Skill, SkillResult

        class SimpleSkill(Skill):
            name = "simple"

            def execute(self, context):
                return SkillResult.ok()

        registry = build_registry()
        skill = SimpleSkill(tool_caller=None)
        checker = SkillPermissionChecker(registry)

        self.assertEqual(checker.highest_permission(skill), Permission.READ_ONLY)


if __name__ == "__main__":
    unittest.main()