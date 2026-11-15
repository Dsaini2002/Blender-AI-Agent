"""Study room run (23:16): seeing what the check found and sent; the Groq key behind the quota switch had expired;
'light_location' was dropped silently; books of different heights were 'fixed' for three rounds."""

from . import _bpy_stub  # noqa: F401

import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent.agent import post_verify as pv
from blender_ai_agent.agent.scene_checks import _uneven_repeats
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.observability.run_trace import build_report
from blender_ai_agent.reliability.friendly_errors import friendly_error_message, is_auth_error
from blender_ai_agent.tools.lighting_tools import CreateLightTool
from .fakes_ext import FakeBridge


def report(folder, **kw):
    r = pv.CheckReport(round=kw.pop("round", 1), folder=folder)
    for k, v in kw.items():
        setattr(r, k, v)
    return r


class TestReviewFiles(unittest.TestCase):

    def test_review_txt_has_everything_the_check_found(self):
        folder = os.path.join(tempfile.mkdtemp(), "20261114_231646_r0")
        r = report(folder, round=0, score=4.0, summary="room is bare", missing=["left wall window"],
                   problems=[{"severity": "high", "where": "whiteboard", "issue": "in the middle of the room",
                              "fix": "move it to the right wall"}],
                   geometry=[{"severity": "high", "where": "bookshelf", "issue": "goes 0.20 m into the wall",
                              "fix": "object.move_by(names=['bookshelf'], offset=[0.25, 0, 0])"}],
                   images=[os.path.join(folder, "check_front.png")], needs_fix=True)
        path = pv.write_review(r, "make a study room")
        text = open(path, encoding="utf-8").read()
        for expected in ("score: 4/10", "missing: left wall window", "[high] whiteboard: in the middle of the room",
                         "fix: move it to the right wall", "goes 0.20 m into the wall", "check_front.png",
                         "fix needed", "make a study room"):
            self.assertIn(expected, text)

    def test_skipped_vision_says_why(self):
        folder = os.path.join(tempfile.mkdtemp(), "r")
        text = open(pv.write_review(report(folder, vision_note="vision check skipped: Gemini quota"), "x")).read()
        self.assertIn("not done - vision check skipped: Gemini quota", text)

    def test_fix_prompt_is_saved_next_to_it_and_logged(self):
        folder = os.path.join(tempfile.mkdtemp(), "r1")
        logged = []
        controller = CopilotController(SimpleNamespace(role_hint="", tool_filter=None), auto_split=False)
        controller._log = lambda event, **data: logged.append((event, data))
        controller._save_fix_prompt(report(folder), "AUTOMATIC CHECK (round 1): fix the window", 1)
        self.assertEqual(open(os.path.join(folder, "fix_prompt.txt")).read(), "AUTOMATIC CHECK (round 1): fix the window")
        self.assertEqual(logged[0][0], "check.fix_sent")
        controller._log_review(report(folder, score=5.0, missing=["plant"], needs_fix=True))
        self.assertEqual(logged[1][1]["missing"], ["plant"])

    def test_report_has_a_section_per_check_round(self):
        payload = {"request": "room", "seconds": 10, "success": True, "events": [
            {"t": "2026-11-14T23:17:46", "event": "check.review", "round": 0, "score": 4.0, "folder": "C:/checks/r0",
             "missing": ["window"], "problems": ["[high] whiteboard: middle of the room -> fix: move it"],
             "geometry": ["[high] bookshelf: into the wall -> fix: object.move_by"], "needs_fix": True},
            {"t": "2026-11-14T23:17:47", "event": "check.fix_sent", "round": 1, "file": "C:/checks/r0/fix_prompt.txt"}]}
        text = build_report(payload)
        self.assertIn("AUTOMATIC CHECK ROUNDS (1)", text)
        self.assertIn("missing: window", text)
        self.assertIn("vision:   [high] whiteboard", text)
        self.assertIn("geometry: [high] bookshelf", text)
        self.assertIn("FIX   round 1 sent to the agent", text)


class TestBadKeyAfterSwitch(unittest.TestCase):

    def test_quota_waits_for_the_same_ai_and_never_switches(self):
        class Agent:
            role_hint, tool_filter = "", None

            def __init__(self):
                self._model_provider = SimpleNamespace(name="gemini")
                self.calls = 0

            def run(self, message, state=None):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("429 Gemini quota is used up (retry in 51058s).")
                return SimpleNamespace(reply_text=f"done with {self._model_provider.name}", task_id="t",
                                       rolled_back=False, stopped_reason="stop")

        agent = Agent()
        controller = CopilotController(agent, auto_split=False)
        controller.current_provider_name = "gemini"
        now = [1000.0]
        controller._quota_clock = lambda: now[0]
        controller._quota_sleep = lambda s: now.__setitem__(0, now[0] + s)
        result = controller._submit("make a desk")
        self.assertEqual(result.reply_text, "done with gemini")
        self.assertEqual(controller.current_provider_name, "gemini")
        self.assertGreaterEqual(now[0] - 1000.0, 51058)                     # it really waited the asked time

    def test_auth_errors_are_explained(self):
        self.assertTrue(is_auth_error("Groq API error 401: Invalid API Key"))
        self.assertFalse(is_auth_error("429 quota"))
        self.assertIn("Submit Key", friendly_error_message("Groq API error 401: Invalid API Key"))


class TestSmall(unittest.TestCase):

    def test_prefixed_argument_names(self):
        result = CreateLightTool(FakeBridge()).execute({"light_location": [0, 1.9, 2.1], "light_type": "POINT",
                                                        "energy": 300, "name": "led"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["location"], [0, 1.9, 2.1])

    def test_books_may_differ_in_height(self):
        boxes = {f"bookshelf_book_{i}": {"min": [i * 0.1, 0, 2.2], "max": [i * 0.1 + 0.05, 0.2, 2.2 + h]}
                 for i, h in enumerate((0.24, 0.24, 0.24, 0.20, 0.24))}
        self.assertEqual(_uneven_repeats(sorted(boxes), boxes), [])
        legs = {f"table_leg_{i}": {"min": [i, 0, 0], "max": [i + 0.05, 0.05, h]} for i, h in enumerate((0.75, 0.75, 0.6))}
        self.assertTrue(_uneven_repeats(sorted(legs), legs))


if __name__ == "__main__":
    unittest.main()
