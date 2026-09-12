from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.decomposer import SubTask
from blender_ai_agent.agent.advanced.task_graph import CyclicDependencyError, TaskGraph


class TestTaskGraph(unittest.TestCase):

    def test_independent_tasks_have_no_dependencies(self):
        subtasks = [
            SubTask(id="1", description="Create floor"),
            SubTask(id="2", description="Create walls"),
            SubTask(id="3", description="Add materials", depends_on=["1", "2"]),
        ]
        graph = TaskGraph(subtasks)

        independent = graph.independent_tasks()
        independent_ids = {t.id for t in independent}

        self.assertEqual(independent_ids, {"1", "2"})

    def test_execution_order_respects_dependencies(self):
        subtasks = [
            SubTask(id="3", description="Assign material", depends_on=["1", "2"]),
            SubTask(id="1", description="Create object"),
            SubTask(id="2", description="Create material", depends_on=["1"]),
        ]
        graph = TaskGraph(subtasks)

        order = [t.id for t in graph.execution_order()]

        self.assertLess(order.index("1"), order.index("2"))
        self.assertLess(order.index("2"), order.index("3"))

    def test_linear_chain_order(self):
        subtasks = [
            SubTask(id="a", description="first"),
            SubTask(id="b", description="second", depends_on=["a"]),
            SubTask(id="c", description="third", depends_on=["b"]),
        ]
        graph = TaskGraph(subtasks)

        order = [t.id for t in graph.execution_order()]
        self.assertEqual(order, ["a", "b", "c"])

    def test_cyclic_dependency_raises(self):
        subtasks = [
            SubTask(id="a", description="first", depends_on=["b"]),
            SubTask(id="b", description="second", depends_on=["a"]),
        ]
        graph = TaskGraph(subtasks)

        with self.assertRaises(CyclicDependencyError):
            graph.execution_order()

    def test_get_task_by_id(self):
        subtasks = [SubTask(id="1", description="only task")]
        graph = TaskGraph(subtasks)

        self.assertEqual(graph.get("1").description, "only task")


if __name__ == "__main__":
    unittest.main()