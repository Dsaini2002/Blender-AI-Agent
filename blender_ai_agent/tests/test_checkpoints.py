from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.checkpoints import CheckpointManager
from .fakes import FakeBridge, FakeObject


class TestCheckpointManager(unittest.TestCase):

    def test_create_checkpoint_captures_current_state(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        manager = CheckpointManager(bridge)

        checkpoint = manager.create_checkpoint("model_complete")

        self.assertEqual(checkpoint.name, "model_complete")
        self.assertIn("Cube", checkpoint.snapshot.object_names())

    def test_list_checkpoints_in_order(self):
        bridge = FakeBridge()
        manager = CheckpointManager(bridge)

        manager.create_checkpoint("step1")
        manager.create_checkpoint("step2")

        self.assertEqual(manager.list_checkpoints(), ["step1", "step2"])

    def test_rollback_to_named_checkpoint(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        manager = CheckpointManager(bridge)
        manager.create_checkpoint("model_complete")

        bridge.create_object(name="BrokenMaterial")  # checkpoint ke baad kuch galat hua

        manager.rollback_to("model_complete")

        self.assertIsNone(bridge.get_object("BrokenMaterial"))
        self.assertIsNotNone(bridge.get_object("Cube"))

    def test_rollback_to_latest_uses_most_recent_checkpoint(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        manager = CheckpointManager(bridge)
        manager.create_checkpoint("step1")

        bridge.create_object(name="Material1")
        manager.create_checkpoint("step2")

        bridge.create_object(name="BrokenCamera")  # step2 ke baad kuch galat hua

        manager.rollback_to_latest()

        self.assertIsNotNone(bridge.get_object("Material1"))  # step2 tak ka kaam bacha
        self.assertIsNone(bridge.get_object("BrokenCamera"))  # broken part hata

    def test_rollback_to_missing_checkpoint_raises(self):
        bridge = FakeBridge()
        manager = CheckpointManager(bridge)

        with self.assertRaises(KeyError):
            manager.rollback_to("does-not-exist")

    def test_rollback_to_latest_with_no_checkpoints_raises(self):
        bridge = FakeBridge()
        manager = CheckpointManager(bridge)

        with self.assertRaises(ValueError):
            manager.rollback_to_latest()


if __name__ == "__main__":
    unittest.main()