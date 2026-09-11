from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.memory.context import MemoryContextBuilder
from blender_ai_agent.memory.models import ProjectMemory, UserPreference
from blender_ai_agent.memory.retriever import MemoryRetriever
from blender_ai_agent.memory.store import InMemoryStore


class TestMemoryContextBuilder(unittest.TestCase):

    def test_empty_when_no_relevant_memories(self):
        retriever = MemoryRetriever(InMemoryStore())
        builder = MemoryContextBuilder(retriever)

        context = builder.build_context("anything")

        self.assertTrue(context.is_empty)

    def test_groups_by_type(self):
        store = InMemoryStore()
        store.save(UserPreference(content="prefers wood materials"))
        store.save(ProjectMemory(content="sci-fi wood themed project", project_id="p1"))

        retriever = MemoryRetriever(store, threshold=0.1)
        builder = MemoryContextBuilder(retriever)

        context = builder.build_context("wood")

        self.assertIn("user_preference", context.by_type)
        self.assertIn("project_memory", context.by_type)

    def test_render_text_readable(self):
        store = InMemoryStore()
        store.save(UserPreference(content="prefers wood materials"))

        retriever = MemoryRetriever(store, threshold=0.1)
        builder = MemoryContextBuilder(retriever)

        context = builder.build_context("wood")
        text = context.render_text()

        self.assertIn("user_preference:", text)
        self.assertIn("prefers wood materials", text)

    def test_render_text_when_empty(self):
        retriever = MemoryRetriever(InMemoryStore())
        builder = MemoryContextBuilder(retriever)

        context = builder.build_context("nothing relevant")

        self.assertEqual(context.render_text(), "No relevant memory.")


if __name__ == "__main__":
    unittest.main()