from . import _bpy_stub  # noqa: F401

import unittest
from unittest.mock import MagicMock, patch

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.providers.gemini_provider import GeminiProvider, RateLimited
from .test_repair_loop import build_repair_loop


def tool_response(*calls):
    return ModelResponse(
        content=None,
        tool_calls=[ToolCall(tool_name=n, arguments=a) for n, a in calls],
        finish_reason="tool_calls",
    )


def text_response(text="done"):
    return ModelResponse(content=text, tool_calls=[], finish_reason="stop")


class TestLoopGuards(unittest.TestCase):

    def test_duplicate_successful_call_is_skipped(self):
        create = ("object.create", {"primitive": "CUBE", "name": "car_body"})
        loop, bridge, _ = build_repair_loop([
            tool_response(create),
            tool_response(create),     # exact repeat -> skipped
            text_response(),
        ])
        result = loop.run("make a car")
        self.assertEqual(result.stopped_reason, "stop")
        self.assertEqual(len(result.executed_steps), 1)   # sirf ek baar execute hua

    def test_repeating_model_is_stopped_early_with_no_progress(self):
        create = ("object.create", {"primitive": "CUBE", "name": "car_body"})
        loop, _, _ = build_repair_loop(
            [tool_response(create)] * 10, max_iterations=25,
        )
        result = loop.run("make a car")
        self.assertEqual(result.stopped_reason, "no_progress")
        self.assertLess(result.turns_used, 6)
        self.assertNotIn("step limit", result.reply_text)

    def test_ledger_lists_completed_work(self):
        loop, _, _ = build_repair_loop([text_response()])
        record = MagicMock()
        record.tool_result.success = True
        record.tool_call.tool_name = "object.create"
        record.tool_call.arguments = {"name": "car_body"}
        ledger = loop._progress_ledger([record])
        self.assertIn("object.create(name=car_body)", ledger)
        self.assertIn("do NOT repeat", ledger)


class TestGeminiFallback(unittest.TestCase):

    def _provider(self, models):
        p = object.__new__(GeminiProvider)
        p._genai = MagicMock()
        p._model_name = "gemini-3.1-pro-preview"
        p._fallback_models = ["gemini-3.5-flash-lite"]
        p._genai.GenerativeModel.side_effect = lambda model_name, tools=None: models[model_name]
        p._build_tools = lambda t: []
        p._build_contents = lambda m: []
        p._parse_response = lambda r: r
        return p

    class _Model:
        def __init__(self, err=None):
            self.err = err

        def generate_content(self, contents):
            if self.err:
                raise RuntimeError(self.err)
            return "OK"

    @patch("blender_ai_agent.providers.gemini_provider.time.sleep")
    def test_long_429_switches_model_without_sleeping(self, mock_sleep):
        models = {
            "gemini-3.1-pro-preview": self._Model("429 Please retry in 55.0s."),
            "gemini-3.5-flash-lite": self._Model(),
        }
        p = self._provider(models)
        req = MagicMock(tools=[], messages=[])
        self.assertEqual(p.generate(req), "OK")
        mock_sleep.assert_not_called()
        self.assertEqual(p._model_name, "gemini-3.5-flash-lite")   # sticky

    @patch("blender_ai_agent.providers.gemini_provider.time.sleep")
    def test_short_429_still_retries_same_model(self, mock_sleep):
        m = self._Model("429 Please retry in 2.0s.")
        calls = {"n": 0}
        orig = m.generate_content

        def flaky(contents):
            calls["n"] += 1
            if calls["n"] == 1:
                return orig(contents)
            return "OK"
        m.generate_content = flaky
        p = self._provider({"gemini-3.1-pro-preview": m})
        p._fallback_models = []
        self.assertEqual(p.generate(MagicMock(tools=[], messages=[])), "OK")
        mock_sleep.assert_called_once()


class TestSceneContextShowsMaterials(unittest.TestCase):

    def test_context_text_includes_material_name(self):
        from blender_ai_agent.agent.context import ContextManager
        tool = MagicMock()
        tool.execute.return_value.success = True
        tool.execute.return_value.data = {"objects": [
            {"name": "car_body", "type": "MESH", "location": [0, 0, 0.5],
             "scale": [1.5, 0.7, 0.25], "materials": ["car_red"]}]}
        text = ContextManager(tool).build_context_text()
        self.assertIn("material=car_red", text)


if __name__ == "__main__":
    unittest.main()
