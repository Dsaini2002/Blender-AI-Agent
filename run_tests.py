"""run_tests.py"""

import sys
import types
import unittest


def _quiet_test_folders():
    """Tests must not write run logs into the real ~/BlenderAIAgent folder."""
    import os
    import tempfile
    os.environ.setdefault("BLENDER_AI_LOG_DIR", tempfile.mkdtemp(prefix="aiagent_test_logs_"))
    os.environ.setdefault("BLENDER_AI_RECENT_FILE", os.path.join(tempfile.mkdtemp(prefix="aiagent_test_recent_"),
                                                                 "recent_tasks.json"))


def install_fake_bpy():
    _quiet_test_folders()
    if "bpy" in sys.modules:
        return

    fake_bpy = types.ModuleType("bpy")

    fake_types = types.ModuleType("bpy.types")
    fake_types.Operator = type("Operator", (), {})
    fake_types.Panel = type("Panel", (), {})

    fake_utils = types.ModuleType("bpy.utils")
    fake_utils.register_class = lambda cls: None
    fake_utils.unregister_class = lambda cls: None

    fake_bpy.types = fake_types
    fake_bpy.utils = fake_utils
    fake_bpy.context = types.SimpleNamespace(scene=None, active_object=None)
    fake_bpy.data = types.SimpleNamespace(objects=[])
    fake_bpy.ops = types.SimpleNamespace()

    sys.modules["bpy"] = fake_bpy
    sys.modules["bpy.types"] = fake_types
    sys.modules["bpy.utils"] = fake_utils


install_fake_bpy()


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(
        start_dir="blender_ai_agent/tests",
        pattern="test_*.py",
        top_level_dir=".",
    )
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)