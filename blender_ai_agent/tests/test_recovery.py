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

    def test_missing_name_argument_fills_in_most_recently_created_object(self):
        """Hinglish: Exact real-world case — LLM ne 'create a cylinder'
        ke baad 'rotate it' bola aur object.transform mein 'name' hi
        nahi bheja. RecoveryManager scene ke sabse recent object ka
        naam bhar deta hai."""
        recovery = build_recovery(objects=[FakeObject(name="car_body"), FakeObject(name="car_wheel_fl")])
        tool_call = ToolCall(tool_name="object.transform", arguments={"rotation": [0, 90, 0]})
        error = ToolError(code=ErrorCode.MISSING_ARGUMENT, message="missing 1 required positional argument: 'name'", recoverable=True)

        corrected = recovery.attempt_recovery(tool_call, error)

        self.assertIsNotNone(corrected)
        self.assertEqual(corrected.arguments["name"], "car_wheel_fl")
        self.assertEqual(corrected.arguments["rotation"], [0, 90, 0])

    def test_missing_object_name_argument_uses_object_name_key_for_material_assign(self):
        recovery = build_recovery(objects=[FakeObject(name="car_body")])
        tool_call = ToolCall(tool_name="material.assign", arguments={"material_name": "car_paint"})
        error = ToolError(code=ErrorCode.MISSING_ARGUMENT, message="missing 1 required positional argument: 'object_name'", recoverable=True)

        corrected = recovery.attempt_recovery(tool_call, error)

        self.assertIsNotNone(corrected)
        self.assertEqual(corrected.arguments["object_name"], "car_body")

    def test_missing_argument_on_unsupported_tool_returns_none(self):
        recovery = build_recovery(objects=[FakeObject(name="car_body")])
        tool_call = ToolCall(tool_name="camera.create", arguments={})
        error = ToolError(code=ErrorCode.MISSING_ARGUMENT, message="missing 1 required positional argument: 'name'", recoverable=True)

        corrected = recovery.attempt_recovery(tool_call, error)
        self.assertIsNone(corrected)

    def test_empty_scene_cannot_recover_missing_argument(self):
        recovery = build_recovery(objects=[])
        tool_call = ToolCall(tool_name="object.transform", arguments={"location": [1, 1, 1]})
        error = ToolError(code=ErrorCode.MISSING_ARGUMENT, message="missing 1 required positional argument: 'name'", recoverable=True)

        corrected = recovery.attempt_recovery(tool_call, error)
        self.assertIsNone(corrected)


if __name__ == "__main__":
    unittest.main()