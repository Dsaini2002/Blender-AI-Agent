from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.material_tools import (
    AssignMaterialTool,
    CreateMaterialTool,
    ModifyMaterialTool,
)
from .fakes import FakeBridge, FakeObject


class TestCreateMaterialTool(unittest.TestCase):

    def test_create_material_success(self):
        bridge = FakeBridge()
        tool = CreateMaterialTool(bridge)
        result = tool.execute({"name": "RedMaterial"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["name"], "RedMaterial")
        self.assertIsNotNone(bridge.get_material("RedMaterial"))

    def test_create_material_with_color(self):
        bridge = FakeBridge()
        tool = CreateMaterialTool(bridge)
        result = tool.execute({"name": "RedMaterial", "color": [1.0, 0.0, 0.0]})

        self.assertTrue(result.success)
        material = bridge.get_material("RedMaterial")
        self.assertEqual(material.color, [1.0, 0.0, 0.0, 1.0])

    def test_invalid_color_length_fails(self):
        bridge = FakeBridge()
        tool = CreateMaterialTool(bridge)
        result = tool.execute({"name": "Bad", "color": [1.0, 0.0]})

        self.assertFalse(result.success)


class TestAssignMaterialTool(unittest.TestCase):

    def test_assign_material_success(self):
        obj = FakeObject(name="Cube")
        bridge = FakeBridge(objects=[obj])
        bridge.create_material("RedMaterial")

        tool = AssignMaterialTool(bridge)
        result = tool.execute({"object_name": "Cube", "material_name": "RedMaterial"})

        self.assertTrue(result.success)
        self.assertEqual(obj.material_name, "RedMaterial")

    def test_assign_missing_object_fails_gracefully(self):
        bridge = FakeBridge()
        bridge.create_material("RedMaterial")

        tool = AssignMaterialTool(bridge)
        result = tool.execute({"object_name": "DoesNotExist", "material_name": "RedMaterial"})

        self.assertFalse(result.success)

    def test_assign_missing_material_fails_gracefully(self):
        obj = FakeObject(name="Cube")
        bridge = FakeBridge(objects=[obj])

        tool = AssignMaterialTool(bridge)
        result = tool.execute({"object_name": "Cube", "material_name": "DoesNotExist"})

        self.assertFalse(result.success)


class TestModifyMaterialTool(unittest.TestCase):

    def test_modify_roughness_and_metallic(self):
        bridge = FakeBridge()
        bridge.create_material("RedMaterial")

        tool = ModifyMaterialTool(bridge)
        result = tool.execute({"name": "RedMaterial", "roughness": 0.2, "metallic": 0.8})

        self.assertTrue(result.success)
        material = bridge.get_material("RedMaterial")
        self.assertEqual(material.roughness, 0.2)
        self.assertEqual(material.metallic, 0.8)

    def test_modify_missing_material_fails_gracefully(self):
        bridge = FakeBridge()
        tool = ModifyMaterialTool(bridge)
        result = tool.execute({"name": "DoesNotExist", "roughness": 0.5})

        self.assertFalse(result.success)

    def test_out_of_range_roughness_fails(self):
        bridge = FakeBridge()
        bridge.create_material("RedMaterial")

        tool = ModifyMaterialTool(bridge)
        result = tool.execute({"name": "RedMaterial", "roughness": 1.5})

        self.assertFalse(result.success)

    def test_no_fields_provided_fails(self):
        bridge = FakeBridge()
        bridge.create_material("RedMaterial")

        tool = ModifyMaterialTool(bridge)
        result = tool.execute({"name": "RedMaterial"})

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()