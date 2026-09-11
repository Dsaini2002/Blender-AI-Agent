from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.benchmarks.dataset_loader import DatasetLoader
from blender_ai_agent.benchmarks.models import Difficulty


class TestDatasetLoader(unittest.TestCase):

    def test_loads_minimal_task(self):
        loader = DatasetLoader()
        task = loader.load_task({"id": "t1", "instruction": "Create a cube."})

        self.assertEqual(task.id, "t1")
        self.assertEqual(task.difficulty, Difficulty.EASY)

    def test_loads_full_task(self):
        loader = DatasetLoader()
        task = loader.load_task({
            "id": "object_create_001",
            "instruction": "Create a cube named Hero.",
            "expected_state": {"objects": [{"name": "Hero", "type": "MESH"}]},
            "validation_rules": ["object_exists", "object_type"],
            "category": "objects",
            "difficulty": "medium",
            "timeout": 60,
        })

        self.assertEqual(task.category, "objects")
        self.assertEqual(task.difficulty, Difficulty.MEDIUM)
        self.assertEqual(task.timeout, 60)

    def test_load_multiple_tasks(self):
        loader = DatasetLoader()
        tasks = loader.load_tasks([
            {"id": "t1", "instruction": "a"},
            {"id": "t2", "instruction": "b"},
        ])

        self.assertEqual(len(tasks), 2)


if __name__ == "__main__":
    unittest.main()