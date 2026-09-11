from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.diff import compute_diff
from blender_ai_agent.reliability.snapshot import SnapshotManager
from .fakes import FakeBridge, FakeObject


class TestComputeDiff(unittest.TestCase):

    def test_no_changes_means_no_diff(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        before = SnapshotManager(bridge).capture()
        after = SnapshotManager(bridge).capture()

        diff = compute_diff(before, after)

        self.assertFalse(diff.has_changes)

    def test_detects_created_object(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        before = SnapshotManager(bridge).capture()

        bridge.create_object(name="Sphere")
        after = SnapshotManager(bridge).capture()

        diff = compute_diff(before, after)

        self.assertEqual(diff.created, ["Sphere"])
        self.assertTrue(diff.has_changes)

    def test_detects_deleted_object(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube"), FakeObject(name="Sphere")])
        before = SnapshotManager(bridge).capture()

        bridge.delete_object("Sphere")
        after = SnapshotManager(bridge).capture()

        diff = compute_diff(before, after)

        self.assertEqual(diff.deleted, ["Sphere"])

    def test_detects_modified_location(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube", location=[0, 0, 0])])
        before = SnapshotManager(bridge).capture()

        bridge.transform_object("Cube", location=[5, 0, 0])
        after = SnapshotManager(bridge).capture()

        diff = compute_diff(before, after)

        self.assertEqual(len(diff.modified), 1)
        self.assertEqual(diff.modified[0].before_location, [0, 0, 0])
        self.assertEqual(diff.modified[0].after_location, [5, 0, 0])


if __name__ == "__main__":
    unittest.main()