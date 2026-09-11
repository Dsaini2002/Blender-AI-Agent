from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.history import TaskHistory


class TestTaskHistory(unittest.TestCase):

    def test_starts_empty(self):
        history = TaskHistory()
        self.assertEqual(len(history), 0)

    def test_add_entry(self):
        history = TaskHistory()
        history.add(task_id="t1", description="Create cube", success=True)

        self.assertEqual(len(history), 1)

    def test_list_recent_returns_newest_first(self):
        history = TaskHistory()
        history.add(task_id="t1", description="first", success=True)
        history.add(task_id="t2", description="second", success=True)

        recent = history.list_recent()

        self.assertEqual(recent[0].description, "second")
        self.assertEqual(recent[1].description, "first")

    def test_list_recent_respects_limit(self):
        history = TaskHistory()
        for i in range(5):
            history.add(task_id=f"t{i}", description=f"task {i}", success=True)

        recent = history.list_recent(limit=2)
        self.assertEqual(len(recent), 2)

    def test_find_by_task_id(self):
        history = TaskHistory()
        history.add(task_id="t1", description="Create cube", success=True)

        entry = history.find_by_task_id("t1")
        self.assertEqual(entry.description, "Create cube")

    def test_find_missing_task_id_returns_none(self):
        history = TaskHistory()
        self.assertIsNone(history.find_by_task_id("does-not-exist"))

    def test_icon_reflects_success(self):
        history = TaskHistory()
        history.add(task_id="t1", description="ok", success=True)
        history.add(task_id="t2", description="bad", success=False)

        entries = history.list_recent()
        self.assertEqual(entries[0].icon, "✗")  # t2, newest
        self.assertEqual(entries[1].icon, "✓")  # t1


if __name__ == "__main__":
    unittest.main()