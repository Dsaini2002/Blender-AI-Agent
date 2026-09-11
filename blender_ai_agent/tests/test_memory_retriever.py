from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.memory.models import Memory
from blender_ai_agent.memory.retriever import MemoryRetriever
from blender_ai_agent.memory.store import InMemoryStore


def build_store_with(*contents):
    store = InMemoryStore()
    for content in contents:
        store.save(Memory(content=content))
    return store


class TestMemoryRetrieverScoring(unittest.TestCase):

    def test_exact_word_match_scores_high(self):
        retriever = MemoryRetriever(InMemoryStore())
        mem = Memory(content="User prefers wood materials for furniture.")

        score = retriever.score("wood materials", mem)

        self.assertEqual(score, 1.0)

    def test_no_overlap_scores_zero(self):
        retriever = MemoryRetriever(InMemoryStore())
        mem = Memory(content="Completely unrelated content.")

        score = retriever.score("wood materials", mem)

        self.assertEqual(score, 0.0)


class TestMemoryRetrieverRetrieve(unittest.TestCase):

    def test_retrieves_only_relevant_memories(self):
        store = build_store_with(
            "User prefers wood materials.",
            "Previous dining table workflow used wood.",
            "Old camera experiment with wide lens.",
        )
        retriever = MemoryRetriever(store, threshold=0.3)

        results = retriever.retrieve("wood dining table")

        contents = [m.content for m in results]
        self.assertTrue(any("wood" in c.lower() for c in contents))
        self.assertFalse(any("camera" in c.lower() for c in contents))

    def test_respects_limit(self):
        store = build_store_with(*[f"wood material variant {i}" for i in range(10)])
        retriever = MemoryRetriever(store, threshold=0.1)

        results = retriever.retrieve("wood material", limit=3)

        self.assertEqual(len(results), 3)

    def test_empty_store_returns_empty(self):
        retriever = MemoryRetriever(InMemoryStore())
        self.assertEqual(retriever.retrieve("anything"), [])

    def test_results_sorted_by_relevance_descending(self):
        store = build_store_with(
            "wood",
            "wood table dining wood",
        )
        retriever = MemoryRetriever(store, threshold=0.0)

        results = retriever.retrieve("wood table dining")

        self.assertEqual(results[0].content, "wood table dining wood")


if __name__ == "__main__":
    unittest.main()