from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.modifier_tools import (
    AddModifierTool,
    ConfigureModifierTool,
    RemoveModifierTool,
)
from .fakes import FakeBridge, FakeObject


class TestAddModifierTool(unittest.TestCase):

    def test_add_modifier_success(self):
        obj = FakeObject(name="Cube")
        bridge = FakeBridge(objects=[obj])
        tool = AddModifierTool(bridge)

        result = tool.execute({
            "object_name": "Cube",
            "modifier_name": "Bevel1",
            "modifier_type": "BEVEL",
        })

        self.assertTrue(result.success)
        self.assertEqual(result.data["modifier"], "Bevel1")
        self.assertIsNotNone(obj.modifiers.get("Bevel1"))

    def test_add_modifier_missing_object_fails_gracefully(self):
        bridge = FakeBridge(objects=[])
        tool = AddModifierTool(bridge)

        result = tool.execute({"object_name": "DoesNotExist", "modifier_name": "Bevel1"})

        self.assertFalse(result.success)


class TestRemoveModifierTool(unittest.TestCase):

    def test_remove_existing_modifier(self):
        obj = FakeObject(name="Cube")
        obj.modifiers.new(name="Bevel1", type="BEVEL")
        bridge = FakeBridge(objects=[obj])
        tool = RemoveModifierTool(bridge)

        result = tool.execute({"object_name": "Cube", "modifier_name": "Bevel1"})

        self.assertTrue(result.success)
        self.assertIsNone(obj.modifiers.get("Bevel1"))

    def test_remove_missing_modifier_fails_gracefully(self):
        obj = FakeObject(name="Cube")
        bridge = FakeBridge(objects=[obj])
        tool = RemoveModifierTool(bridge)

        result = tool.execute({"object_name": "Cube", "modifier_name": "DoesNotExist"})

        self.assertFalse(result.success)

    def test_permission_is_destructive(self):
        tool = RemoveModifierTool(FakeBridge())
        from blender_ai_agent.tools.base import Permission
        self.assertEqual(tool.permission, Permission.DESTRUCTIVE)


class TestConfigureModifierTool(unittest.TestCase):

    def test_configure_modifier_success(self):
        obj = FakeObject(name="Cube")
        obj.modifiers.new(name="Bevel1", type="BEVEL")
        bridge = FakeBridge(objects=[obj])
        tool = ConfigureModifierTool(bridge)

        result = tool.execute({
            "object_name": "Cube",
            "modifier_name": "Bevel1",
            "properties": {"width": 0.05},
        })

        self.assertTrue(result.success)
        modifier = obj.modifiers.get("Bevel1")
        self.assertEqual(modifier.width, 0.05)

    def test_configure_missing_modifier_fails_gracefully(self):
        obj = FakeObject(name="Cube")
        bridge = FakeBridge(objects=[obj])
        tool = ConfigureModifierTool(bridge)

        result = tool.execute({
            "object_name": "Cube",
            "modifier_name": "DoesNotExist",
            "properties": {"width": 0.05},
        })

        self.assertFalse(result.success)

    def test_empty_properties_fails_validation(self):
        obj = FakeObject(name="Cube")
        obj.modifiers.new(name="Bevel1", type="BEVEL")
        bridge = FakeBridge(objects=[obj])
        tool = ConfigureModifierTool(bridge)

        result = tool.execute({
            "object_name": "Cube",
            "modifier_name": "Bevel1",
            "properties": {},
        })

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()