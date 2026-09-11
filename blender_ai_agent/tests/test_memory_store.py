from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.memory.models import Memory
from blender_ai_agent.memory.store import InMemoryStore, MemoryStore


class TestMemoryStoreBase(unittest.TestCase):

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            MemoryStore()


class TestInMemoryStore(unittest.TestCase):

    def test_save_and_get(self):
        store = InMemoryStore()
        mem = Memory(content="test memory")
        store.save(mem)

        retrieved = store.get(mem.id)
        self.assertEqual(retrieved.content, "test memory")

    def test_get_missing_returns_none(self):
        store = InMemoryStore()
        self.assertIsNone(store.get("does-not-exist"))

    def test_search_finds_matching_content(self):
        store = InMemoryStore()
        store.save(Memory(content="User prefers wood materials."))
        store.save(Memory(content="User likes metallic finishes."))

        results = store.search("wood")

        self.assertEqual(len(results), 1)
        self.assertIn("wood", results[0].content.lower())

    def test_delete_removes_memory(self):
        store = InMemoryStore()
        mem = Memory(content="temporary")
        store.save(mem)

        deleted = store.delete(mem.id)

        self.assertTrue(deleted)
        self.assertIsNone(store.get(mem.id))

    def test_delete_missing_returns_false(self):
        store = InMemoryStore()
        self.assertFalse(store.delete("does-not-exist"))

    def test_all_returns_every_memory(self):
        store = InMemoryStore()
        store.save(Memory(content="one"))
        store.save(Memory(content="two"))

        self.assertEqual(len(store.all()), 2)


if __name__ == "__main__":
    unittest.main()