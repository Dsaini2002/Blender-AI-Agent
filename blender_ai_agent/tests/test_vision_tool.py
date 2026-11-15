from . import _bpy_stub  # noqa: F401

import tempfile
import unittest
import os

from blender_ai_agent.vision.tool import VisionObserveInput


class TestVisionObserveDefaultPath(unittest.TestCase):

    def test_default_filepath_uses_system_temp_dir_not_hardcoded_unix_tmp(self):
        inp = VisionObserveInput()
        self.assertTrue(inp.filepath.startswith(tempfile.gettempdir()))

    def test_default_filepath_ends_with_expected_filename(self):
        inp = VisionObserveInput()
        self.assertTrue(os.path.basename(inp.filepath) == "vision_observe.png")

    def test_explicit_filepath_still_overrides_default(self):
        inp = VisionObserveInput(filepath="C:\\Users\\test\\preview.png")
        self.assertEqual(inp.filepath, "C:\\Users\\test\\preview.png")


if __name__ == "__main__":
    unittest.main()