from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import ToolCall
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.reliability.errors import ErrorCode, ToolError
from blender_ai_agent.reliability.recovery import RecoveryManager
from blender_ai_agent.tools.object_tools import TransformObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge, FakeObject


def build_recovery(objects):
    bridge = FakeBridge(objects=objects)
    registry = ToolRegistry()
    registry.register(TransformObjectTool(bridge))
    inspector = SceneInspector(bridge)
    registry.register(SceneInspectTool(inspector))
    tool_caller = ToolCaller(registry)
    return RecoveryManager(tool_caller)


class TestRecoveryManager(unittest.TestCase):

    def test_finds_similar_object_name(self):
        recovery = build_recovery(objects=[FakeObject(name="Red_Cube")])
        tool_call = ToolCall(tool_name="object.transform", arguments={"name": "RedCube", "location": [5, 0, 0]})
        error = ToolError(code=ErrorCode.OBJECT_NOT_FOUND, message="not found", recoverable=True)

        corrected = recovery.attempt_recovery(tool_call, error)

        self.assertIsNotNone(corrected)
        self.assertEqual(corrected.arguments["name"], "Red_Cube")

    def test_no_similar_object_returns_none(self):
        recovery = build_recovery(objects=[FakeObject(name="Camera")])
        tool_call = ToolCall(tool_name="object.transform", arguments={"name": "Cube", "location": [1, 1, 1]})
        error = ToolError(code=ErrorCode.OBJECT_NOT_FOUND, message="not found", recoverable=True)

        corrected = recovery.attempt_recovery(tool_call, error)
        self.assertIsNone(corrected)

    def test_non_recoverable_error_type_returns_none(self):
        recovery = build_recovery(objects=[])
        tool_call = ToolCall(tool_name="object.create", arguments={})
        error = ToolError(code=ErrorCode.INVALID_INPUT, message="bad input", recoverable=False)

        corrected = recovery.attempt_recovery(tool_call, error)
        self.assertIsNone(corrected)


if __name__ == "__main__":
    unittest.main()