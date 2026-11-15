from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.python_power_tool import PythonPowerTool
from .fakes import FakeBridge, FakeObject


class TestPythonPowerTool(unittest.TestCase):

    def test_permission_is_python_execution(self):
        tool = PythonPowerTool(FakeBridge())
        self.assertEqual(tool.permission, Permission.PYTHON_EXECUTION)

    def test_import_keyword_blocked(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": "import os"})

        self.assertFalse(result.success)
        self.assertIn("blocked", result.error.lower())
        
    def test_import_bpy_is_allowed(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": "import bpy\nresult = 1"})

        self.assertTrue(result.success)

    def test_dunder_access_blocked(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": "result = ().__class__"})

        self.assertFalse(result.success)

    def test_disallowed_bpy_module_blocked(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": "bpy.data.objects.remove(None)"})

        self.assertFalse(result.success)

    def test_empty_code_fails_validation(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": ""})

        self.assertFalse(result.success)

    def test_file_save_blocked(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": "bpy.ops.wm.save_as(filepath='x.blend')"})

        self.assertFalse(result.success)

    def test_blenderkit_search_call_passes_sandbox_check(self):
        code = 'bpy.ops.view3d.blenderkit_search(keywords="human")\nresult = 1'
        self.assertTrue(PythonPowerTool._uses_only_allowed_bpy(code))

    def test_blenderkit_download_call_passes_sandbox_check(self):
        code = "bpy.ops.scene.blenderkit_download()\nresult = 1"
        self.assertTrue(PythonPowerTool._uses_only_allowed_bpy(code))

    def test_unrelated_blenderkit_looking_op_still_blocked(self):
        code = "bpy.ops.scene.blenderkit_upload()\nresult = 1"
        self.assertFalse(PythonPowerTool._uses_only_allowed_bpy(code))

    def test_view3d_digit_in_name_does_not_truncate_match(self):
        code = "bpy.ops.view3d.blenderkit_search(keywords='x')"
        self.assertTrue(PythonPowerTool._uses_only_allowed_bpy(code))


if __name__ == "__main__":
    unittest.main()