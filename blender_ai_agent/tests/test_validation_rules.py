from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.validation_rules import (
    MaterialRule,
    ModifierRule,
    ObjectExistsRule,
    ObjectTypeRule,
    TransformRule,
)
from .fakes import FakeBridge, FakeObject


class TestObjectExistsRule(unittest.TestCase):

    def test_existing_object_passes(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        result = ObjectExistsRule("Hero").validate(bridge)
        self.assertTrue(result.passed)

    def test_missing_object_fails(self):
        bridge = FakeBridge(objects=[])
        result = ObjectExistsRule("Hero").validate(bridge)
        self.assertFalse(result.passed)


class TestObjectTypeRule(unittest.TestCase):

    def test_matching_type_passes(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero", type_="MESH")])
        result = ObjectTypeRule("Hero", "MESH").validate(bridge)
        self.assertTrue(result.passed)

    def test_wrong_type_fails(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero", type_="CAMERA")])
        result = ObjectTypeRule("Hero", "MESH").validate(bridge)
        self.assertFalse(result.passed)


class TestTransformRule(unittest.TestCase):

    def test_matching_location_within_tolerance_passes(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero", location=[3.005, 0, 0])])
        result = TransformRule("Hero", "x", 3.0, tolerance=0.01).validate(bridge)
        self.assertTrue(result.passed)

    def test_mismatched_location_fails(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero", location=[2.7, 0, 0])])
        result = TransformRule("Hero", "x", 3.0).validate(bridge)
        self.assertFalse(result.passed)

    def test_missing_object_fails(self):
        bridge = FakeBridge(objects=[])
        result = TransformRule("Hero", "x", 3.0).validate(bridge)
        self.assertFalse(result.passed)


class TestMaterialRule(unittest.TestCase):

    def test_correct_material_passes(self):
        obj = FakeObject(name="Hero")
        obj.material_name = "Red"
        bridge = FakeBridge(objects=[obj])
        result = MaterialRule("Hero", "Red").validate(bridge)
        self.assertTrue(result.passed)

    def test_wrong_material_fails(self):
        obj = FakeObject(name="Hero")
        obj.material_name = "Blue"
        bridge = FakeBridge(objects=[obj])
        result = MaterialRule("Hero", "Red").validate(bridge)
        self.assertFalse(result.passed)


class TestModifierRule(unittest.TestCase):

    def test_matching_modifier_passes(self):
        obj = FakeObject(name="Hero")
        obj.modifiers.new(name="Bevel1", type="BEVEL")
        bridge = FakeBridge(objects=[obj])
        result = ModifierRule("Hero", "Bevel1", "BEVEL").validate(bridge)
        self.assertTrue(result.passed)

    def test_missing_modifier_fails(self):
        bridge = FakeBridge(objects=[FakeObject(name="Hero")])
        result = ModifierRule("Hero", "Bevel1", "BEVEL").validate(bridge)
        self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()