from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.memory.manager import MemoryManager
from blender_ai_agent.memory.models import Memory, UserPreference
from blender_ai_agent.memory.store import InMemoryStore


class TestMemoryManager(unittest.TestCase):

    def test_remember_and_recall(self):
        manager = MemoryManager(InMemoryStore())
        manager.remember(UserPreference(content="User prefers wood materials."))

        results = manager.recall("wood")

        self.assertEqual(len(results), 1)

    def test_recall_no_match_returns_empty(self):
        manager = MemoryManager(InMemoryStore())
        manager.remember(Memory(content="unrelated content"))

        results = manager.recall("wood")

        self.assertEqual(results, [])

    def test_forget_removes_memory(self):
        manager = MemoryManager(InMemoryStore())
        mem = Memory(content="temporary preference")
        manager.remember(mem)

        forgotten = manager.forget(mem.id)

        self.assertTrue(forgotten)
        self.assertIsNone(manager.get(mem.id))

    def test_get_by_id(self):
        manager = MemoryManager(InMemoryStore())
        mem = Memory(content="findable")
        manager.remember(mem)

        found = manager.get(mem.id)

        self.assertEqual(found.content, "findable")

    def test_manager_does_not_care_about_store_implementation(self):
        """Hinglish: Dependency Inversion verify — kaisi bhi MemoryStore subclass chale."""
        class FakeStore(InMemoryStore):
            pass

        manager = MemoryManager(FakeStore())
        manager.remember(Memory(content="works with any store"))

        self.assertEqual(len(manager.recall("works")), 1)


if __name__ == "__main__":
    unittest.main()