from . import _bpy_stub  # noqa: F401

import threading
import unittest

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.autonomy.guardrails import GuardrailLimits
from blender_ai_agent.autonomy.modes import AutonomyMode
from blender_ai_agent.copilot.approval import ApprovalGate, approval_question
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.tools.object_tools import CreateObjectTool, DeleteObjectTool
from blender_ai_agent.tools.python_power_tool import PythonPowerTool
from .fakes import FakeBridge
from .test_repair_loop import build_repair_loop


def create(name):
    return ModelResponse(tool_calls=[ToolCall("object.create", {"name": name, "primitive": "CUBE"})])


class TestGuardrailsInTheLoop(unittest.TestCase):

    def test_step_limit_stops_and_keeps_the_work(self):
        loop, bridge, _ = build_repair_loop([create(f"C{i}") for i in range(6)] + [ModelResponse(content="done")],
                                            max_iterations=10)
        loop._guardrails = GuardrailLimits(max_steps=2, max_retries=5, max_runtime_seconds=60, max_scene_changes=100)
        result = loop.run("make six cubes")
        self.assertEqual(result.stopped_reason, "guardrail")
        self.assertIn("safety limit", result.reply_text)
        self.assertIsNotNone(bridge.get_object("C0"))          # committed, not rolled back
        self.assertIsNone(bridge.get_object("C5"))

    def test_scene_change_limit(self):
        loop, bridge, _ = build_repair_loop([create(f"C{i}") for i in range(5)] + [ModelResponse(content="done")],
                                            max_iterations=10)
        loop._guardrails = GuardrailLimits(max_steps=100, max_retries=5, max_runtime_seconds=60, max_scene_changes=2)
        result = loop.run("make cubes")
        self.assertEqual(result.stopped_reason, "guardrail")
        self.assertIn("more objects", result.reply_text)

    def test_controller_reports_a_guardrail_stop_as_stopped(self):
        loop, _, _ = build_repair_loop([create("A"), create("B"), ModelResponse(content="done")], max_iterations=10)
        loop._guardrails = GuardrailLimits(max_steps=1, max_retries=5, max_runtime_seconds=60, max_scene_changes=100)
        result = CopilotController(loop, auto_split=False).submit("make cubes")
        self.assertFalse(result.success)
        self.assertTrue(result.reply_text.startswith("Stopped"))

    def test_no_limits_by_default(self):
        loop, _, _ = build_repair_loop([create("A"), ModelResponse(content="done")])
        self.assertEqual(loop.run("make a cube").stopped_reason, "stop")


class TestAutonomyModes(unittest.TestCase):

    def setUp(self):
        bridge = FakeBridge()
        self.create, self.delete, self.python = CreateObjectTool(bridge), DeleteObjectTool(bridge), PythonPowerTool(bridge)

    def ask(self, tool, call, mode, existing=("Cube",)):
        return approval_question(call, tool, existing, mode)

    def test_manual_asks_for_every_change(self):
        self.assertIn("Creating objects", self.ask(self.create, ToolCall("object.create", {"name": "A"}), AutonomyMode.MANUAL))

    def test_assisted_asks_only_for_python_and_user_objects(self):
        self.assertIsNone(self.ask(self.create, ToolCall("object.create", {"name": "A"}), AutonomyMode.ASSISTED))
        self.assertIsNotNone(self.ask(self.delete, ToolCall("object.delete", {"name": "Cube"}), AutonomyMode.ASSISTED))

    def test_autonomous_asks_only_for_python(self):
        self.assertIsNone(self.ask(self.delete, ToolCall("object.delete", {"name": "Cube"}), AutonomyMode.AUTONOMOUS))
        self.assertIsNotNone(self.ask(self.python, ToolCall("python.execute", {"code": "x = 1"}), AutonomyMode.AUTONOMOUS))

    def test_allow_all_answers_the_rest_of_the_request(self):
        gate = ApprovalGate()
        threading.Timer(0.05, gate.allow_all).start()
        self.assertTrue(gate.request("first?", timeout=2))
        self.assertTrue(gate.request("second?", timeout=0.01))
        gate.reset()
        self.assertFalse(gate.request("third?", timeout=0.01))


if __name__ == "__main__":
    unittest.main()
