"""15 Nov: 'gemini se kitna token milta hai, kitna use hua, kitna waste gaya' - every answer's tokens are counted per
run (by phase) and per day; wasted requests are marked."""

from . import _bpy_stub  # noqa: F401

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent.observability import token_meter as tm


class TokenMeterTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"BLENDER_AI_LOG_DIR": os.path.join(self.tmp.name, "logs")})
        self.env.start()
        tm.start_run()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_run_totals_phases_and_waste(self):
        tm.set_phase("plan")
        tm.record("gemini", "gemini-3.6-flash", 4000, 300)
        tm.set_phase("build")
        tm.record("gemini", "gemini-3.6-flash", 12000, 500)
        tm.mark_waste("a step where the AI only repeated calls")
        tm.set_phase("fix 1")
        tm.record("gemini", "gemini-3.6-flash", 13000, 200)
        tm.mark_waste("fix round 1 brought no improvement", tm.phase_tokens("fix 1"))
        tm.record_failure("gemini", "gemini-3.6-flash", "429 quota")
        text = tm.summary()
        self.assertIn("AI use: 3 request(s), 30,000 tokens (29,000 in / 1,000 out)", text)
        self.assertIn("plan 1, build 1, fix 1 1", text)
        self.assertIn("1 failed request(s)", text)
        self.assertIn("Wasted: 25,700 tokens (86%)", text)
        self.assertIn("Today (gemini gemini-3.6-flash): 4 request(s), 30,000 tokens, 1 failed, quota ran out at", text)
        self.assertIn("wasted: fix round 1 brought no improvement (13,200 tokens)", tm.details())
        with open(tm.usage_path(), encoding="utf-8") as handle:
            day = next(iter(json.load(handle).values()))
        self.assertEqual(day["gemini gemini-3.6-flash"]["requests"], 4)
        self.assertEqual(os.path.dirname(tm.usage_path()), self.tmp.name)       # next to logs/, not inside

    def test_providers_report_their_answers(self):
        from blender_ai_agent.providers.base import _meter
        reply = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=18000, completion_tokens=400))
        self.assertIs(_meter("claude", "claude-sonnet-5-5", reply), reply)
        self.assertEqual((tm.RUN["requests"], tm.RUN["input"]), (1, 18000))
        _meter("claude", "x", object())                      # an answer without usage never breaks a request
        self.assertEqual(tm.RUN["requests"], 2)

    def test_nothing_used_says_nothing(self):
        self.assertEqual(tm.summary(), "")


if __name__ == "__main__":
    unittest.main()
