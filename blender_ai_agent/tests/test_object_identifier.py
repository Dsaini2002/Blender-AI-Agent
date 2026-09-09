from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.vision.identifier import ObjectIdentifier
from .fakes import FakeBridge, FakeObject


class TestObjectIdentifier(unittest.TestCase):

    def test_identifies_matching_object_by_name_words(self):
        bridge = FakeBridge(objects=[FakeObject(name="Red_Cube"), FakeObject(name="Blue_Sphere")])
        identifier = ObjectIdentifier(bridge)

        result = identifier.identify("the red cube on the left")

        self.assertEqual(result, "Red_Cube")

    def test_no_match_returns_none(self):
        bridge = FakeBridge(objects=[FakeObject(name="Camera")])
        identifier = ObjectIdentifier(bridge)

        result = identifier.identify("a flying dragon")

        self.assertIsNone(result)

    def test_identify_all_multiple_descriptions(self):
        bridge = FakeBridge(objects=[FakeObject(name="Red_Cube"), FakeObject(name="Blue_Sphere")])
        identifier = ObjectIdentifier(bridge)

        results = identifier.identify_all(["red cube", "blue sphere"])

        self.assertEqual(results["red cube"], "Red_Cube")
        self.assertEqual(results["blue sphere"], "Blue_Sphere")

    def test_empty_scene_returns_none(self):
        bridge = FakeBridge(objects=[])
        identifier = ObjectIdentifier(bridge)

        self.assertIsNone(identifier.identify("anything"))


if __name__ == "__main__":
    unittest.main()