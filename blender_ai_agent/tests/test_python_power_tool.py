from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.python_power_tool import PythonPowerTool
from .fakes import FakeBridge, FakeObject


class TestPythonPowerTool(unittest.TestCase):

    def test_permission_is_python_execution(self):
        tool = PythonPowerTool(FakeBridge())
        self.assertEqual(tool.permission, Permission.PYTHON_EXECUTION)

    def test_simple_code_executes_successfully(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        tool = PythonPowerTool(bridge)

        result = tool.execute({"code": "result = len(bridge.get_objects())"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["result"], 1)

    def test_import_keyword_blocked(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": "import os"})

        self.assertFalse(result.success)
        self.assertIn("blocked", result.error.lower())

    def test_dunder_access_blocked(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": "result = ().__class__"})

        self.assertFalse(result.success)

    def test_runtime_error_fails_gracefully(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": "result = 1 / 0"})

        self.assertFalse(result.success)
        self.assertIn("Python execution failed", result.error)

    def test_empty_code_fails_validation(self):
        tool = PythonPowerTool(FakeBridge())
        result = tool.execute({"code": ""})

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()