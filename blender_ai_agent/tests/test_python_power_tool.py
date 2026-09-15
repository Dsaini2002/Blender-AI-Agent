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


if __name__ == "__main__":
    unittest.main()