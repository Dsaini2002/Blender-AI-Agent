from . import _bpy_stub  # noqa: F401

import threading
import unittest

from blender_ai_agent.agent.models import ToolCall
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.copilot.approval import ApprovalGate, approval_question, make_approver
from blender_ai_agent.reliability.transaction import TransactionManager
from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tests.fakes_ext import FakeBridge
from blender_ai_agent.tools.object_tools import CreateObjectTool, DeleteObjectTool
from blender_ai_agent.tools.python_power_tool import PythonPowerTool
from blender_ai_agent.tools.registry import ToolRegistry


def caller(bridge):
    registry = ToolRegistry()
    for tool in (CreateObjectTool(bridge), DeleteObjectTool(bridge), PythonPowerTool(bridge)):
        registry.register(tool)
    return ToolCaller(registry), registry


class TestApprovalQuestions(unittest.TestCase):

    def setUp(self):
        self.bridge = FakeBridge(objects=[FakeObject("UserCube")])
        self.caller, self.registry = caller(self.bridge)

    def test_python_and_deleting_user_objects_need_approval(self):
        python = ToolCall("python.execute", {"code": "bpy.ops.object.select_all(action='DESELECT')"})
        self.assertIn("Python", approval_question(python, self.registry.get("python.execute"), []))
        delete_user = ToolCall("object.delete", {"name": "UserCube"})
        self.assertIn("UserCube", approval_question(delete_user, self.registry.get("object.delete"), ["UserCube"]))

    def test_deleting_its_own_new_object_and_safe_tools_do_not_ask(self):
        delete_new = ToolCall("object.delete", {"name": "TempPart"})
        self.assertIsNone(approval_question(delete_new, self.registry.get("object.delete"), ["UserCube"]))
        create = ToolCall("object.create", {"name": "A", "primitive": "CUBE"})
        self.assertIsNone(approval_question(create, self.registry.get("object.create"), ["UserCube"]))

    def test_denied_call_is_not_executed(self):
        gate = ApprovalGate()
        self.caller.approver = make_approver(gate, ["UserCube"])
        threading.Timer(0.05, lambda: gate.answer(False)).start()
        result = self.caller.call(ToolCall("object.delete", {"name": "UserCube"}))
        self.assertFalse(result.success)
        self.assertTrue(result.error.startswith("Not run:"))
        self.assertIsNotNone(self.bridge.get_object("UserCube"))

    def test_allowed_call_runs(self):
        gate = ApprovalGate()
        self.caller.approver = make_approver(gate, ["UserCube"])
        threading.Timer(0.05, lambda: gate.answer(True)).start()
        result = self.caller.call(ToolCall("object.delete", {"name": "UserCube"}))
        self.assertTrue(result.success, result.error)
        self.assertIsNone(self.bridge.get_object("UserCube"))

    def test_gate_times_out_as_deny(self):
        self.assertFalse(ApprovalGate().request("?", timeout=0.01))


class TestPythonToolBlocksDataAccess(unittest.TestCase):

    def test_blend_data_and_delete_bypasses_are_blocked(self):
        tool = PythonPowerTool(FakeBridge())
        for code in ("bpy.context.blend_data.objects.remove(x)", "bpy.ops.object.delete()",
                     "getattr(bpy, 'data')", "bpy.data.meshes.new('x')"):
            result = tool.execute({"code": code})
            self.assertFalse(result.success, code)
            self.assertIn("blocked", result.error.lower(), code)


class TestRollbackRestoresModifiersAndMaterials(unittest.TestCase):

    def test_modifier_and_material_changes_are_undone(self):
        bridge = FakeBridge(objects=[FakeObject("Chair")])
        bridge.create_material("Wood")
        bridge.create_material("Red")
        bridge.assign_material("Chair", "Wood")
        transaction = TransactionManager(bridge)
        transaction.begin()
        bridge.add_modifier("Chair", "Bevel", "BEVEL")
        bridge.assign_material("Chair", "Red")
        bridge.create_object("NewPart")
        report = transaction.rollback()
        chair = bridge.get_object("Chair")
        self.assertIsNone(chair.modifiers.get("Bevel"))
        self.assertEqual(chair.material_name, "Wood")
        self.assertIsNone(bridge.get_object("NewPart"))
        self.assertIn("Chair:Bevel", report.removed_modifiers)
        self.assertIn("Chair", report.restored_materials)


if __name__ == "__main__":
    unittest.main()
