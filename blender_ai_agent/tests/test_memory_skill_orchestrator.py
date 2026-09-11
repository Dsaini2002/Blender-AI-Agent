from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.memory.context import MemoryContextBuilder
from blender_ai_agent.memory.manager import MemoryManager
from blender_ai_agent.memory.models import UserPreference
from blender_ai_agent.memory.orchestrator import MemorySkillOrchestrator
from blender_ai_agent.memory.retriever import MemoryRetriever
from blender_ai_agent.memory.store import InMemoryStore
from blender_ai_agent.skills.builtins.product_showcase import ProductShowcaseSkill
from blender_ai_agent.skills.registry import SkillRegistry
from blender_ai_agent.tools.camera_tools import CreateCameraTool
from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool
from blender_ai_agent.tools.object_tools import CreateObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from .fakes import FakeBridge


def build_orchestrator(with_memory=True):
    bridge = FakeBridge()
    tool_registry = ToolRegistry()
    tool_registry.register(CreateObjectTool(bridge))
    tool_registry.register(CreateMaterialTool(bridge))
    tool_registry.register(AssignMaterialTool(bridge))
    tool_registry.register(CreateCameraTool(bridge))
    tool_caller = ToolCaller(tool_registry)

    skill_registry = SkillRegistry()
    skill_registry.register(ProductShowcaseSkill(tool_caller))

    store = InMemoryStore()
    if with_memory:
        manager = MemoryManager(store)
        manager.remember(UserPreference(content="User prefers dark studio product showcase setup."))

    retriever = MemoryRetriever(store, threshold=0.1)
    context_builder = MemoryContextBuilder(retriever)

    return MemorySkillOrchestrator(skill_registry, context_builder), bridge


class TestMemorySkillOrchestrator(unittest.TestCase):

    def test_matching_skill_executes_with_memory_applied(self):
        orchestrator, bridge = build_orchestrator(with_memory=True)

        result = orchestrator.handle_task(
            "create a product showcase",
            base_context={"object_name": "Vase"},
        )

        self.assertEqual(result.skill_used, "product_showcase")
        self.assertTrue(result.memory_applied)
        self.assertTrue(result.skill_result.success)
        self.assertIsNotNone(bridge.get_object("Vase"))

    def test_no_memory_still_executes_skill(self):
        orchestrator, bridge = build_orchestrator(with_memory=False)

        result = orchestrator.handle_task("create a product showcase")

        self.assertEqual(result.skill_used, "product_showcase")
        self.assertFalse(result.memory_applied)
        self.assertTrue(result.skill_result.success)

    def test_no_matching_skill_returns_none(self):
        orchestrator, _ = build_orchestrator()

        result = orchestrator.handle_task("do something totally unrelated to any skill")

        self.assertIsNone(result.skill_used)
        self.assertIsNone(result.skill_result)


if __name__ == "__main__":
    unittest.main()