from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import ToolCall
from blender_ai_agent.tools.object_tools import CreateObjectTool, DeleteObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.vision.human_in_loop import HumanInTheLoopGate
from .fakes import FakeBridge


def build_gate():
    bridge = FakeBridge()
    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(DeleteObjectTool(bridge))
    return HumanInTheLoopGate(registry)


class TestHumanInTheLoopGate(unittest.TestCase):

    def test_safe_write_does_not_require_confirmation(self):
        gate = build_gate()
        tool_call = ToolCall(tool_name="object.create", arguments={"name": "Cube"})

        request = gate.check(tool_call, reason="Vision suggests adding an object.")

        self.assertFalse(request.requires_confirmation)

    def test_destructive_requires_confirmation(self):
        gate = build_gate()
        tool_call = ToolCall(tool_name="object.delete", arguments={"name": "Cube"})

        request = gate.check(tool_call, reason="Vision suggests this object looks unnecessary.")

        self.assertTrue(request.requires_confirmation)
        self.assertIn("unnecessary", request.reason)

    def test_can_auto_proceed_for_safe_write(self):
        gate = build_gate()
        tool_call = ToolCall(tool_name="object.create", arguments={"name": "Cube"})
        self.assertTrue(gate.can_auto_proceed(tool_call))

    def test_cannot_auto_proceed_for_destructive(self):
        gate = build_gate()
        tool_call = ToolCall(tool_name="object.delete", arguments={"name": "Cube"})
        self.assertFalse(gate.can_auto_proceed(tool_call))


if __name__ == "__main__":
    unittest.main()