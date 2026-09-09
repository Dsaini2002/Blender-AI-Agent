from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability.tool_validators import (
    MaterialAssignedValidator,
    ObjectDeletedValidator,
    ObjectExistsValidator,
    TransformValidator,
)
from .fakes import FakeBridge, FakeObject


class TestObjectExistsValidator(unittest.TestCase):

    def test_object_exists_and_correct_type_is_valid(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube", type_="MESH")])
        result = ObjectExistsValidator().validate({"name": "Cube", "object_type": "MESH"}, bridge)
        self.assertTrue(result.valid)

    def test_missing_object_is_invalid(self):
        bridge = FakeBridge(objects=[])
        result = ObjectExistsValidator().validate({"name": "Cube"}, bridge)
        self.assertFalse(result.valid)

    def test_wrong_type_is_invalid(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube", type_="CAMERA")])
        result = ObjectExistsValidator().validate({"name": "Cube", "object_type": "MESH"}, bridge)
        self.assertFalse(result.valid)


class TestObjectDeletedValidator(unittest.TestCase):

    def test_deleted_object_is_valid(self):
        bridge = FakeBridge(objects=[])
        result = ObjectDeletedValidator().validate({"name": "Cube"}, bridge)
        self.assertTrue(result.valid)

    def test_still_existing_object_is_invalid(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        result = ObjectDeletedValidator().validate({"name": "Cube"}, bridge)
        self.assertFalse(result.valid)


class TestTransformValidator(unittest.TestCase):

    def test_matching_location_is_valid(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube", location=[3, 0, 0])])
        result = TransformValidator().validate({"name": "Cube", "location": [3, 0, 0]}, bridge)
        self.assertTrue(result.valid)

    def test_mismatched_location_is_invalid(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube", location=[0, 0, 0])])
        result = TransformValidator().validate({"name": "Cube", "location": [3, 0, 0]}, bridge)
        self.assertFalse(result.valid)

    def test_missing_object_is_invalid(self):
        bridge = FakeBridge(objects=[])
        result = TransformValidator().validate({"name": "Cube", "location": [1, 1, 1]}, bridge)
        self.assertFalse(result.valid)


class TestMaterialAssignedValidator(unittest.TestCase):

    def test_correct_material_is_valid(self):
        obj = FakeObject(name="Cube")
        obj.material_name = "Red"
        bridge = FakeBridge(objects=[obj])
        result = MaterialAssignedValidator().validate({"object_name": "Cube", "material_name": "Red"}, bridge)
        self.assertTrue(result.valid)

    def test_wrong_material_is_invalid(self):
        obj = FakeObject(name="Cube")
        obj.material_name = "Blue"
        bridge = FakeBridge(objects=[obj])
        result = MaterialAssignedValidator().validate({"object_name": "Cube", "material_name": "Red"}, bridge)
        self.assertFalse(result.valid)


if __name__ == "__main__":
    unittest.main()