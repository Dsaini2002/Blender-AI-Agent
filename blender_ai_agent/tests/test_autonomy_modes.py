from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.autonomy.modes import AutonomyMode, AutonomyPolicy
from blender_ai_agent.tools.base import Permission


class TestAutonomyPolicy(unittest.TestCase):

    def test_default_mode_is_assisted(self):
        policy = AutonomyPolicy()
        self.assertEqual(policy.mode, AutonomyMode.ASSISTED)

    def test_manual_mode_confirms_everything(self):
        policy = AutonomyPolicy(AutonomyMode.MANUAL)
        self.assertTrue(policy.requires_confirmation(Permission.READ_ONLY))
        self.assertTrue(policy.requires_confirmation(Permission.SAFE_WRITE))

    def test_assisted_mode_auto_approves_safe_operations(self):
        policy = AutonomyPolicy(AutonomyMode.ASSISTED)
        self.assertFalse(policy.requires_confirmation(Permission.READ_ONLY))
        self.assertFalse(policy.requires_confirmation(Permission.SAFE_WRITE))

    def test_assisted_mode_confirms_destructive(self):
        policy = AutonomyPolicy(AutonomyMode.ASSISTED)
        self.assertTrue(policy.requires_confirmation(Permission.DESTRUCTIVE))

    def test_autonomous_mode_auto_approves_destructive(self):
        policy = AutonomyPolicy(AutonomyMode.AUTONOMOUS)
        self.assertFalse(policy.requires_confirmation(Permission.DESTRUCTIVE))

    def test_autonomous_mode_still_confirms_python_execution(self):
        """Security-critical: kabhi bhi fully-unattended raw code execution nahi."""
        policy = AutonomyPolicy(AutonomyMode.AUTONOMOUS)
        self.assertTrue(policy.requires_confirmation(Permission.PYTHON_EXECUTION))


if __name__ == "__main__":
    unittest.main()