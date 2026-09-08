"""
Integration Test — Step 2.8
==============================
Hinglish: Ab tak humne har tool ko ALAG-ALAG (isolated) test kiya.
Ye test poore system ko EK SAATH assemble karke check karta hai —
jaisa asli addon mein `_register_tools()` karta hai.

Isse confirm hota hai:
  - Saare 14 tools bina naam-clash ke register ho sakte hain
  - Har tool ka permission/description sahi set hai
  - End-to-end flow kaam karta hai: create object -> add material ->
    add modifier -> sab ek hi bridge/registry ke through
"""

from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from blender_ai_agent.tools.object_tools import (
    CreateObjectTool,
    DeleteObjectTool,
    DuplicateObjectTool,
    RenameObjectTool,
    TransformObjectTool,
)
from blender_ai_agent.tools.material_tools import (
    CreateMaterialTool,
    AssignMaterialTool,
    ModifyMaterialTool,
)
from blender_ai_agent.tools.modifier_tools import (
    AddModifierTool,
    RemoveModifierTool,
    ConfigureModifierTool,
)
from blender_ai_agent.tools.camera_tools import (
    CreateCameraTool,
    SetCameraTool,
    RenderPreviewTool,
)
from .fakes import FakeBridge


def build_registry(bridge):
    """
    Hinglish: Ye function exactly wahi kaam karta hai jo root
    __init__.py ka `_register_tools()` karta hai — Composition Root
    ka test-friendly version.
    """
    registry = ToolRegistry()
    inspector = SceneInspector(bridge)

    registry.register(SceneInspectTool(inspector))

    registry.register(CreateObjectTool(bridge))
    registry.register(DeleteObjectTool(bridge))
    registry.register(DuplicateObjectTool(bridge))
    registry.register(RenameObjectTool(bridge))
    registry.register(TransformObjectTool(bridge))

    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))
    registry.register(ModifyMaterialTool(bridge))

    registry.register(AddModifierTool(bridge))
    registry.register(RemoveModifierTool(bridge))
    registry.register(ConfigureModifierTool(bridge))

    registry.register(CreateCameraTool(bridge))
    registry.register(SetCameraTool(bridge))
    registry.register(RenderPreviewTool(bridge))

    return registry


class TestFullToolRegistration(unittest.TestCase):

    def test_all_14_tools_register_without_conflict(self):
        registry = build_registry(FakeBridge())
        self.assertEqual(len(registry.list_tools()), 15)

    def test_expected_tool_names_present(self):
        registry = build_registry(FakeBridge())
        tool_names = set(registry.list_tools())

        expected = {
            "scene.inspect",
            "object.create", "object.delete", "object.duplicate",
            "object.rename", "object.transform",
            "material.create", "material.assign", "material.modify",
            "modifier.add", "modifier.remove", "modifier.configure",
            "camera.create", "camera.set", "render.preview",
        }

        self.assertEqual(tool_names, expected)

    def test_every_tool_has_name_and_description(self):
        """Har tool ka metadata complete hona chahiye — Agent (Phase 3) isi pe depend karega."""
        registry = build_registry(FakeBridge())

        for tool_name in registry.list_tools():
            tool = registry.get(tool_name)
            self.assertTrue(tool.name, f"{tool_name} has empty name")
            self.assertTrue(tool.description, f"{tool_name} has empty description")


class TestEndToEndWorkflow(unittest.TestCase):
    """
    Hinglish: Ek realistic sequence test — jaisa future mein Agent
    multiple tools chain karega.
    """

    def test_create_object_then_add_material_then_modifier(self):
        bridge = FakeBridge()
        registry = build_registry(bridge)

        # Step 1: Cube banao
        create_result = registry.get("object.create").execute({"name": "Cube"})
        self.assertTrue(create_result.success)

        # Step 2: Red material banao aur assign karo
        registry.get("material.create").execute({"name": "Red", "color": [1, 0, 0]})
        assign_result = registry.get("material.assign").execute({
            "object_name": "Cube", "material_name": "Red"
        })
        self.assertTrue(assign_result.success)

        # Step 3: Bevel modifier add karo
        modifier_result = registry.get("modifier.add").execute({
            "object_name": "Cube", "modifier_name": "Bevel1", "modifier_type": "BEVEL"
        })
        self.assertTrue(modifier_result.success)

        # Step 4: Verify — scene.inspect se poori state dekho
        inspect_result = registry.get("scene.inspect").execute({})
        self.assertTrue(inspect_result.success)
        object_names = [obj["name"] for obj in inspect_result.data["objects"]]
        self.assertIn("Cube", object_names)


if __name__ == "__main__":
    unittest.main()