from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.orchestration.task_manager import InvalidTaskTransition, TaskManager, TaskState
from .fakes import FakeBridge, FakeObject


class TestTaskManager(unittest.TestCase):

    def test_new_task_starts_queued(self):
        manager = TaskManager(FakeBridge())
        task = manager.create_task("t1", "Create a cube.")

        self.assertEqual(task.state, TaskState.QUEUED)

    def test_start_transitions_to_running(self):
        manager = TaskManager(FakeBridge())
        manager.create_task("t1", "Create a cube.")
        manager.start("t1")

        self.assertEqual(manager.get_task("t1").state, TaskState.RUNNING)

    def test_pause_creates_checkpoint_and_transitions(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        manager = TaskManager(bridge)
        manager.create_task("t1", "Long task")
        manager.start("t1")

        manager.pause("t1")

        task = manager.get_task("t1")
        self.assertEqual(task.state, TaskState.PAUSED)
        self.assertTrue(task.pause_checkpoint_name.startswith("pause_"))

    def test_resume_after_pause(self):
        manager = TaskManager(FakeBridge())
        manager.create_task("t1", "Long task")
        manager.start("t1")
        manager.pause("t1")

        manager.resume("t1")

        self.assertEqual(manager.get_task("t1").state, TaskState.RUNNING)

    def test_complete_from_running(self):
        manager = TaskManager(FakeBridge())
        manager.create_task("t1", "task")
        manager.start("t1")
        manager.complete("t1")

        self.assertEqual(manager.get_task("t1").state, TaskState.COMPLETED)

    def test_invalid_transition_raises(self):
        manager = TaskManager(FakeBridge())
        manager.create_task("t1", "task")

        with self.assertRaises(InvalidTaskTransition):
            manager.complete("t1")  # QUEUED se seedha COMPLETED galat hai

    def test_cannot_transition_from_terminal_state(self):
        manager = TaskManager(FakeBridge())
        manager.create_task("t1", "task")
        manager.start("t1")
        manager.complete("t1")

        with self.assertRaises(InvalidTaskTransition):
            manager.start("t1")


if __name__ == "__main__":
    unittest.main()