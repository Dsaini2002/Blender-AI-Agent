from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.decomposer import SubTask
from blender_ai_agent.agent.advanced.task_graph import TaskGraph


class TestParallelGroups(unittest.TestCase):

    def test_independent_tasks_in_same_level(self):
        subtasks = [
            SubTask(id="body", description="Create body"),
            SubTask(id="arms", description="Create arms", depends_on=["body"]),
            SubTask(id="head", description="Create head", depends_on=["body"]),
            SubTask(id="materials", description="Add materials", depends_on=["arms", "head"]),
        ]
        graph = TaskGraph(subtasks)

        levels = graph.parallel_groups()
        level_ids = [[t.id for t in level] for level in levels]

        self.assertEqual(level_ids[0], ["body"])
        self.assertEqual(set(level_ids[1]), {"arms", "head"})  # ye dono ek saath ho sakte hain
        self.assertEqual(level_ids[2], ["materials"])

    def test_fully_independent_tasks_all_in_one_level(self):
        subtasks = [
            SubTask(id="a", description="task a"),
            SubTask(id="b", description="task b"),
            SubTask(id="c", description="task c"),
        ]
        graph = TaskGraph(subtasks)

        levels = graph.parallel_groups()

        self.assertEqual(len(levels), 1)
        self.assertEqual(len(levels[0]), 3)

    def test_linear_chain_gives_one_task_per_level(self):
        subtasks = [
            SubTask(id="a", description="first"),
            SubTask(id="b", description="second", depends_on=["a"]),
            SubTask(id="c", description="third", depends_on=["b"]),
        ]
        graph = TaskGraph(subtasks)

        levels = graph.parallel_groups()

        self.assertEqual(len(levels), 3)
        self.assertEqual([len(level) for level in levels], [1, 1, 1])


if __name__ == "__main__":
    unittest.main()