"""The 'what happened' files: live_trace.txt while a run goes, <time>_report.txt after it."""

from . import _bpy_stub  # noqa: F401

import json
import os
import tempfile
import unittest
from unittest import mock

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.observability import run_trace
from blender_ai_agent.observability.logger import Logger
from .test_repair_loop import build_repair_loop


class TraceCase(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.env = mock.patch.dict(os.environ, {"BLENDER_AI_LOG_DIR": self.folder})
        self.env.start()

    def tearDown(self):
        run_trace.end_file()
        self.env.stop()

    def live(self):
        with open(os.path.join(self.folder, "live_trace.txt"), encoding="utf-8") as handle:
            return handle.read()


class TestLiveTrace(TraceCase):

    def test_every_step_is_on_disk_while_running(self):
        run_trace.begin("make a hostel", "claude", "claude-sonnet-5-5")
        logger = Logger()
        logger.info("model.request", turn=1)
        text = self.live()                                       # read while the run is still going
        self.assertIn("make a hostel", text)
        self.assertIn("waiting for the AI model's reply", text.splitlines()[-1])
        logger.info("model.plan", turn=1, planned_tools="['mesh.building']")
        logger.info("tool.execute", tool="mesh.building", arguments="{'floors': 6}")
        logger.error("tool.failed", tool="mesh.building", code="BAD", message="floors must be 1-40")
        run_trace.note("CHECK  vision 7/10")
        text = self.live()
        self.assertIn("TOOL   mesh.building {'floors': 6}", text)
        self.assertIn("ERROR", text)
        self.assertIn("floors must be 1-40", text)
        self.assertIn("CHECK  vision 7/10", text)

    def test_exception_traceback_and_finish(self):
        run_trace.begin("x")
        try:
            raise ValueError("boom")
        except ValueError as exc:
            run_trace.exception("the run", exc)
        run_trace.end_file("Done 1/1 steps")
        text = self.live()
        self.assertIn("EXCEPTION in the run: ValueError: boom", text)
        self.assertIn("Traceback", text)
        self.assertIn("FINISHED: Done 1/1 steps", text)

    def test_no_trace_outside_a_run(self):
        run_trace.on_event("tool.execute", {"tool": "x"})
        run_trace.note("nothing")
        self.assertFalse(os.path.exists(os.path.join(self.folder, "live_trace.txt")))

    def test_keys_are_never_written(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "secret-123"}):
            run_trace.begin("x")
            run_trace.end_file("ok")
        text = self.live()
        self.assertNotIn("secret-123", text)
        self.assertIn("GEMINI_API_KEY", text)                    # only that a key is set


class TestReport(TraceCase):

    def test_report_lists_errors_with_arguments_and_time(self):
        payload = {"request": "hostel", "seconds": 12.0, "success": False, "reply": "Done 1/2 steps",
                   "provider": "gemini", "model": "m", "events": [
                       {"t": "2026-11-14T18:05:21.000", "event": "task.start", "message": "hostel"},
                       {"t": "2026-11-14T18:05:21.100", "event": "model.request", "turn": 1},
                       {"t": "2026-11-14T18:05:24.100", "event": "model.plan", "planned_tools": "['material.recipe']"},
                       {"t": "2026-11-14T18:05:24.200", "event": "tool.execute", "tool": "material.recipe",
                        "arguments": "{'recipe': 'grass'}"},
                       {"t": "2026-11-14T18:05:24.300", "event": "error.tool.failed", "tool": "material.recipe",
                        "code": "MISSING_ARGUMENT", "message": "missing 'name'", "arguments": "{'recipe': 'grass'}"}]}
        text = run_trace.build_report(payload, {"blender": "5.2.1"})
        self.assertIn("Result     FAILED", text)
        self.assertIn("ERRORS (1)", text)
        self.assertIn("MISSING_ARGUMENT", text)
        self.assertIn("arguments: {'recipe': 'grass'}", text)
        self.assertIn("waiting for the AI model      3.0 s", text)
        self.assertIn("blender", text)

    def test_controller_writes_report_and_live_trace(self):
        loop, _bridge, _ = build_repair_loop([
            ModelResponse(tool_calls=[ToolCall("object.create", {"name": "Box", "primitive": "CUBE"})]),
            ModelResponse(content="made a box")], max_iterations=4)
        controller = CopilotController(loop, auto_split=False)
        result = controller.submit("make a box")
        self.assertTrue(result.success)
        self.assertTrue(controller.last_report_path.endswith("_report.txt"))
        with open(controller.last_report_path, encoding="utf-8") as handle:
            report = handle.read()
        self.assertIn("make a box", report)
        self.assertIn("TOOL  object.create", report)
        live = self.live()
        self.assertIn("TOOL   object.create", live)
        self.assertIn("FINISHED: made a box", live)


if __name__ == "__main__":
    unittest.main()
