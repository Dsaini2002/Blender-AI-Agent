from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability.snapshot import SnapshotManager
from .fakes import FakeBridge, FakeObject


class TestSnapshotManager(unittest.TestCase):

    def test_captures_all_objects(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube"), FakeObject(name="Sphere")])
        snapshot = SnapshotManager(bridge).capture()

        self.assertEqual(snapshot.object_names(), ["Cube", "Sphere"])

    def test_captures_location_rotation_scale(self):
        obj = FakeObject(name="Cube", location=[1, 2, 3], rotation=[0.1, 0, 0], scale=[2, 2, 2])
        bridge = FakeBridge(objects=[obj])
        snapshot = SnapshotManager(bridge).capture()
        captured = snapshot.get_object("Cube")

        self.assertEqual(captured.location, [1, 2, 3])
        self.assertEqual(captured.rotation, [0.1, 0, 0])
        self.assertEqual(captured.scale, [2, 2, 2])

    def test_empty_scene_snapshot(self):
        bridge = FakeBridge(objects=[])
        snapshot = SnapshotManager(bridge).capture()
        self.assertEqual(snapshot.objects, [])

    def test_get_missing_object_returns_none(self):
        bridge = FakeBridge(objects=[])
        snapshot = SnapshotManager(bridge).capture()
        self.assertIsNone(snapshot.get_object("DoesNotExist"))


if __name__ == "__main__":
    unittest.main()