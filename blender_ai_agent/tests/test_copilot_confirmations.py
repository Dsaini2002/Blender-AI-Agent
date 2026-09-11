from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import ToolCall
from blender_ai_agent.copilot.confirmations import ConfirmationManager, ConfirmationStatus
from blender_ai_agent.tools.object_tools import CreateObjectTool, DeleteObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from .fakes import FakeBridge


def build_manager():
    bridge = FakeBridge()
    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(DeleteObjectTool(bridge))
    return ConfirmationManager(registry)


class TestConfirmationManager(unittest.TestCase):

    def test_request_confirmation_creates_pending(self):
        manager = build_manager()
        tool_call = ToolCall(tool_name="object.delete", arguments={"name": "Cube"})

        confirmation = manager.request_confirmation(tool_call, reason="Cleaning up unused objects.")

        self.assertEqual(confirmation.status, ConfirmationStatus.PENDING)
        self.assertTrue(confirmation.action_id)

    def test_approve_changes_status(self):
        manager = build_manager()
        tool_call = ToolCall(tool_name="object.delete", arguments={"name": "Cube"})
        confirmation = manager.request_confirmation(tool_call)

        manager.approve(confirmation.action_id)

        self.assertTrue(manager.is_approved(confirmation.action_id))

    def test_reject_changes_status(self):
        manager = build_manager()
        tool_call = ToolCall(tool_name="object.delete", arguments={"name": "Cube"})
        confirmation = manager.request_confirmation(tool_call)

        manager.reject(confirmation.action_id)

        self.assertFalse(manager.is_approved(confirmation.action_id))

    def test_unknown_action_id_raises(self):
        manager = build_manager()
        with self.assertRaises(KeyError):
            manager.approve("does-not-exist")

    def test_is_approved_false_for_pending(self):
        manager = build_manager()
        tool_call = ToolCall(tool_name="object.create", arguments={"name": "Cube"})
        confirmation = manager.request_confirmation(tool_call)

        self.assertFalse(manager.is_approved(confirmation.action_id))


if __name__ == "__main__":
    unittest.main()