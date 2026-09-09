from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability.rollback import RollbackManager
from blender_ai_agent.reliability.snapshot import SnapshotManager
from .fakes import FakeBridge, FakeObject


class TestRollbackManager(unittest.TestCase):

    def test_deletes_newly_created_objects(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        snapshot = SnapshotManager(bridge).capture()

        bridge.create_object(name="Sphere")  # snapshot ke baad bana

        report = RollbackManager(bridge).rollback_to(snapshot)

        self.assertIn("Sphere", report.deleted_new_objects)
        self.assertIsNone(bridge.get_object("Sphere"))
        self.assertIsNotNone(bridge.get_object("Cube"))

    def test_restores_transform_changes(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube", location=[0, 0, 0])])
        snapshot = SnapshotManager(bridge).capture()

        bridge.transform_object("Cube", location=[5, 5, 5])

        report = RollbackManager(bridge).rollback_to(snapshot)

        self.assertIn("Cube", report.restored_transforms)
        self.assertEqual(bridge.get_object("Cube").location, [0, 0, 0])

    def test_reports_objects_that_cannot_be_restored(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        snapshot = SnapshotManager(bridge).capture()

        bridge.delete_object("Cube")  # snapshot ke baad delete ho gaya

        report = RollbackManager(bridge).rollback_to(snapshot)

        self.assertIn("Cube", report.could_not_restore)
        self.assertFalse(report.is_clean)

    def test_clean_rollback_when_nothing_changed(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        snapshot = SnapshotManager(bridge).capture()

        report = RollbackManager(bridge).rollback_to(snapshot)

        self.assertTrue(report.is_clean)
        self.assertEqual(report.deleted_new_objects, [])


if __name__ == "__main__":
    unittest.main()