from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.memory.models import Memory, ProjectMemory, TaskMemory, UserPreference


class TestMemory(unittest.TestCase):

    def test_valid_memory_has_defaults(self):
        mem = Memory(content="User prefers wood materials.")
        self.assertTrue(mem.id)
        self.assertEqual(mem.type, "generic")
        self.assertTrue(mem.created_at)

    def test_empty_content_raises(self):
        with self.assertRaises(ValueError):
            Memory(content="")

    def test_matches_query_case_insensitive(self):
        mem = Memory(content="User prefers Wood materials.")
        self.assertTrue(mem.matches_query("wood"))
        self.assertFalse(mem.matches_query("metal"))

    def test_unique_ids_generated(self):
        mem1 = Memory(content="a")
        mem2 = Memory(content="b")
        self.assertNotEqual(mem1.id, mem2.id)


class TestUserPreference(unittest.TestCase):

    def test_type_is_user_preference(self):
        pref = UserPreference(content="Always use dark materials.")
        self.assertEqual(pref.type, "user_preference")


class TestProjectMemory(unittest.TestCase):

    def test_requires_project_id(self):
        with self.assertRaises(ValueError):
            ProjectMemory(content="Sci-fi environment.", project_id="")

    def test_valid_project_memory(self):
        mem = ProjectMemory(content="Sci-fi environment.", project_id="proj_001")
        self.assertEqual(mem.project_id, "proj_001")
        self.assertEqual(mem.type, "project_memory")


class TestTaskMemory(unittest.TestCase):

    def test_type_is_task_memory(self):
        mem = TaskMemory(content="Created spaceship with bevel.")
        self.assertEqual(mem.type, "task_memory")


if __name__ == "__main__":
    unittest.main()