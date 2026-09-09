from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability.transaction import TransactionError, TransactionManager
from .fakes import FakeBridge, FakeObject


class TestTransactionManager(unittest.TestCase):

    def test_begin_then_commit_keeps_changes(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        tx = TransactionManager(bridge)

        tx.begin()
        bridge.create_object(name="Sphere")
        tx.commit()

        self.assertIsNotNone(bridge.get_object("Sphere"))
        self.assertFalse(tx.is_active)

    def test_begin_then_rollback_undoes_changes(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        tx = TransactionManager(bridge)

        tx.begin()
        bridge.create_object(name="Sphere")
        report = tx.rollback()

        self.assertIsNone(bridge.get_object("Sphere"))
        self.assertFalse(tx.is_active)
        self.assertIn("Sphere", report.deleted_new_objects)

    def test_double_begin_raises(self):
        tx = TransactionManager(FakeBridge())
        tx.begin()

        with self.assertRaises(TransactionError):
            tx.begin()

    def test_commit_without_begin_raises(self):
        tx = TransactionManager(FakeBridge())

        with self.assertRaises(TransactionError):
            tx.commit()

    def test_rollback_without_begin_raises(self):
        tx = TransactionManager(FakeBridge())

        with self.assertRaises(TransactionError):
            tx.rollback()


if __name__ == "__main__":
    unittest.main()