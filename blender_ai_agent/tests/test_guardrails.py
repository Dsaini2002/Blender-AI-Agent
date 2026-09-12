from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.autonomy.guardrails import GuardrailLimits, GuardrailMonitor, GuardrailViolation


class TestGuardrailLimits(unittest.TestCase):

    def test_invalid_max_steps_raises(self):
        with self.assertRaises(ValueError):
            GuardrailLimits(max_steps=0)

    def test_invalid_max_retries_raises(self):
        with self.assertRaises(ValueError):
            GuardrailLimits(max_retries=-1)


class TestGuardrailMonitor(unittest.TestCase):

    def test_within_limits_initially(self):
        monitor = GuardrailMonitor()
        self.assertTrue(monitor.is_within_limits)

    def test_max_steps_violation_detected(self):
        monitor = GuardrailMonitor(GuardrailLimits(max_steps=2))
        monitor.record_step()
        monitor.record_step()
        monitor.record_step()  # 3rd — exceeds limit of 2

        self.assertEqual(monitor.check(), GuardrailViolation.MAX_STEPS_EXCEEDED)

    def test_max_retries_violation_detected(self):
        monitor = GuardrailMonitor(GuardrailLimits(max_retries=1))
        monitor.record_retry()
        monitor.record_retry()

        self.assertEqual(monitor.check(), GuardrailViolation.MAX_RETRIES_EXCEEDED)

    def test_max_runtime_violation_detected(self):
        monitor = GuardrailMonitor(GuardrailLimits(max_runtime_seconds=10.0))

        self.assertEqual(monitor.check(elapsed_seconds=15.0), GuardrailViolation.MAX_RUNTIME_EXCEEDED)

    def test_max_scene_changes_violation_detected(self):
        monitor = GuardrailMonitor(GuardrailLimits(max_scene_changes=1))
        monitor.record_scene_change()
        monitor.record_scene_change()

        self.assertEqual(monitor.check(), GuardrailViolation.MAX_SCENE_CHANGES_EXCEEDED)

    def test_no_violation_within_all_limits(self):
        monitor = GuardrailMonitor(GuardrailLimits(max_steps=10, max_retries=5))
        monitor.record_step()
        monitor.record_retry()

        self.assertIsNone(monitor.check(elapsed_seconds=5.0))


if __name__ == "__main__":
    unittest.main()