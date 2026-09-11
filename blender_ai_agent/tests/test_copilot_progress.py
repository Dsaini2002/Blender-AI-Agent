from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.progress import ProgressState, StepStatus


class TestProgressState(unittest.TestCase):

    def test_set_plan_creates_pending_steps(self):
        progress = ProgressState()
        progress.set_plan(["object.create", "material.create"])

        self.assertEqual(progress.total_count, 2)
        self.assertTrue(all(s.status == StepStatus.PENDING for s in progress.steps))

    def test_start_and_complete_step(self):
        progress = ProgressState()
        progress.set_plan(["object.create"])

        progress.start_step(0)
        self.assertEqual(progress.steps[0].status, StepStatus.RUNNING)
        self.assertEqual(progress.current_step_index, 0)

        progress.complete_step(0, success=True)
        self.assertEqual(progress.steps[0].status, StepStatus.COMPLETED)

    def test_failed_step(self):
        progress = ProgressState()
        progress.set_plan(["object.create"])
        progress.start_step(0)
        progress.complete_step(0, success=False)

        self.assertEqual(progress.steps[0].status, StepStatus.FAILED)

    def test_completed_count(self):
        progress = ProgressState()
        progress.set_plan(["a", "b", "c"])
        progress.complete_step(0, success=True)
        progress.complete_step(1, success=True)

        self.assertEqual(progress.completed_count, 2)

    def test_is_complete_true_when_all_steps_resolved(self):
        progress = ProgressState()
        progress.set_plan(["a", "b"])
        progress.complete_step(0, success=True)
        progress.complete_step(1, success=False)

        self.assertTrue(progress.is_complete)

    def test_is_complete_false_with_pending_steps(self):
        progress = ProgressState()
        progress.set_plan(["a", "b"])
        progress.complete_step(0, success=True)

        self.assertFalse(progress.is_complete)

    def test_render_text_shows_icons(self):
        progress = ProgressState()
        progress.set_plan(["object.create"])
        progress.complete_step(0, success=True)

        self.assertIn("✓ object.create", progress.render_text())


if __name__ == "__main__":
    unittest.main()