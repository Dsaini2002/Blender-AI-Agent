from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.copilot import activity
from blender_ai_agent.copilot.controller import CopilotController
from .test_repair_loop import build_repair_loop


def create(name):
    return ModelResponse(tool_calls=[ToolCall("object.create", {"name": name, "primitive": "CUBE"})])


class TestStopButton(unittest.TestCase):

    def test_stop_ends_the_run_and_keeps_what_was_built(self):
        loop, bridge, _ = build_repair_loop([create("A"), create("B"), create("C"), ModelResponse(content="done")])
        calls = {"n": 0}

        def should_stop():
            calls["n"] += 1
            return bridge.get_object("A") is not None          # press Stop right after the first part exists

        loop.should_stop = should_stop
        result = loop.run("make three cubes")
        self.assertEqual(result.stopped_reason, "cancelled")
        self.assertIn("Stopped by user", result.reply_text)
        self.assertIsNotNone(bridge.get_object("A"))            # committed, not rolled back
        self.assertIsNone(bridge.get_object("B"))

    def test_controller_cancel_reaches_the_running_loop(self):
        loop, bridge, _ = build_repair_loop([create("A"), create("B"), ModelResponse(content="done")])
        controller = CopilotController(loop, auto_split=False)
        original = loop._execute_with_repair

        def execute_then_cancel(*args, **kwargs):
            record = original(*args, **kwargs)
            controller.cancel()
            return record

        loop._execute_with_repair = execute_then_cancel
        result = controller.submit("make two cubes")
        self.assertFalse(result.success)
        self.assertTrue(result.reply_text.startswith("Stopped"))
        self.assertIsNone(bridge.get_object("B"))

    def test_stop_flag_only_counts_during_a_run(self):
        activity.end_run()
        activity.request_stop()
        self.assertFalse(activity.stop_requested())
        activity.begin_run()
        activity.request_stop()
        self.assertTrue(activity.stop_requested())
        activity.end_run()
        self.assertFalse(activity.stop_requested())


if __name__ == "__main__":
    unittest.main()
