from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.decomposer import TaskDecomposer


class TestTaskDecomposer(unittest.TestCase):

    def test_known_keyword_decomposes_into_multiple_subtasks(self):
        decomposer = TaskDecomposer()
        subtasks = decomposer.decompose("Create a product showcase for the vase.")

        self.assertGreater(len(subtasks), 1)
        descriptions = [t.description for t in subtasks]
        self.assertIn("Create object", descriptions)

    def test_unknown_instruction_stays_atomic(self):
        decomposer = TaskDecomposer()
        subtasks = decomposer.decompose("Rename Cube to Hero.")

        self.assertEqual(len(subtasks), 1)
        self.assertEqual(subtasks[0].description, "Rename Cube to Hero.")

    def test_subtasks_have_dependencies(self):
        decomposer = TaskDecomposer()
        subtasks = decomposer.decompose("Create a product showcase.")

        assign_step = next(t for t in subtasks if t.description == "Assign material")
        self.assertIn("1", assign_step.depends_on)
        self.assertIn("2", assign_step.depends_on)

    def test_custom_recipes_can_be_injected(self):
        from blender_ai_agent.agent.advanced.decomposer import SubTask

        custom = {"custom task": [SubTask(id="1", description="Do the custom thing")]}
        decomposer = TaskDecomposer(recipes=custom)

        subtasks = decomposer.decompose("please do the custom task now")
        self.assertEqual(subtasks[0].description, "Do the custom thing")


if __name__ == "__main__":
    unittest.main()