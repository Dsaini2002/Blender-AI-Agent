from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.reliability.friendly_errors import (
    friendly_error_message, is_quota_error, quota_message,
)
from blender_ai_agent.tools.base import Permission, Tool, ToolResult
from .test_repair_loop import build_repair_loop

# Exactly the error from the user's screenshot (Gemini free tier, daily limit)
GEMINI_DAILY_429 = (
    "Tool 'vision.observe' failed: 429 You exceeded your current quota, please check your plan and billing "
    "details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. "
    "* Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, "
    "limit: 20, model: gemini-3.6-flash\nPlease retry in 6.871308817s. [links {\n description: \"Learn more\"\n}\n"
    ", violations {\n quota_metric: \"generativelanguage.googleapis.com/generate_content_free_tier_requests\"\n"
    " quota_id: \"GenerateRequestsPerDayPerProjectPerModel-FreeTier\"\n quota_dimensions {\n key: \"model\"\n"
    " value: \"gemini-3.6-flash\"\n }\n quota_value: 20\n}\n, retry_delay {\n seconds: 6\n}\n]"
)

GEMINI_PER_MINUTE_429 = (
    "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: generativelanguage.googleapis.com/"
    "generate_content_free_tier_requests, limit: 5, model: gemini-3.6-flash. Please retry in 31.3s. "
    "quota_id: \"GenerateRequestsPerMinutePerProjectPerModel-FreeTier\""
)


class TestIsQuotaError(unittest.TestCase):

    def test_detects_quota_and_rate_limit_errors(self):
        for text in (GEMINI_DAILY_429, GEMINI_PER_MINUTE_429, "Rate limit reached for gpt",
                     "Error 429: Too Many Requests", "RESOURCE_EXHAUSTED", "You exceeded your current quota"):
            self.assertTrue(is_quota_error(text), text)

    def test_ignores_normal_errors(self):
        for text in ("Object 'Cube' not found", "RetopologyInput.target_faces must be an integer",
                     "Unknown tool: foo", "", None):
            self.assertFalse(is_quota_error(text), text)


class TestFriendlyMessage(unittest.TestCase):

    def test_daily_quota_message_says_it_is_finished(self):
        message = friendly_error_message(GEMINI_DAILY_429)
        self.assertIn("Gemini ka quota khatam ho gaya hai", message)
        self.assertIn("gemini-3.6-flash", message)
        self.assertIn("20 requests/din", message)
        self.assertIn("dusra model", message)

    def test_screenshot_noise_is_gone(self):
        message = friendly_error_message(GEMINI_DAILY_429)
        for noise in ("violations", "quota_dimensions", "retry_delay", "https://", "links {", "429"):
            self.assertNotIn(noise, message)
        self.assertLess(len(message), 220)

    def test_per_minute_limit_says_how_long_to_wait(self):
        message = friendly_error_message(GEMINI_PER_MINUTE_429)
        self.assertIn("requests/minute", message)
        self.assertIn("32 second", message)
        self.assertNotIn("khatam", message)

    def test_vision_step_gets_a_clarifying_suffix(self):
        self.assertIn("visual check skip", friendly_error_message(GEMINI_DAILY_429, tool_name="vision.observe"))
        self.assertNotIn("visual check", friendly_error_message(GEMINI_DAILY_429, tool_name="object.create"))

    def test_other_providers_are_named(self):
        self.assertIn("Groq", quota_message("429 Rate limit reached on groq.com"))
        self.assertIn("OpenAI", quota_message("429 You exceeded your current quota (openai)"))
        self.assertIn("AI provider", quota_message("429 Too Many Requests"))

    def test_non_quota_errors_are_kept_but_shortened(self):
        self.assertEqual(friendly_error_message("Object 'X' not found"), "Object 'X' not found")
        long_error = "boom " * 200
        self.assertLessEqual(len(friendly_error_message(long_error)), 225)
        self.assertEqual(friendly_error_message("first line\nsecond line"), "first line")
        self.assertEqual(friendly_error_message(None), "Task could not be completed.")


class QuotaVisionTool(Tool):
    name = "vision.observe"
    description = "fake vision tool that always hits the Gemini quota"
    permission = Permission.READ_ONLY
    input_model = None
    calls = 0

    def run(self, validated_input):
        QuotaVisionTool.calls += 1
        return ToolResult.fail(GEMINI_DAILY_429)


class TestVisionQuotaDoesNotDestroyTheBuild(unittest.TestCase):
    """Screenshot bug: quota hit in the OPTIONAL vision check rolled back the whole task."""

    def _loop(self, responses):
        loop, bridge, logger = build_repair_loop(responses, max_iterations=6)
        QuotaVisionTool.calls = 0
        loop._tool_caller._registry.register(QuotaVisionTool())
        return loop, bridge, logger

    def test_scene_is_kept_and_reply_explains_quota(self):
        loop, bridge, _ = self._loop([
            ModelResponse(
                tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Cube2"}),
                            ToolCall(tool_name="vision.observe", arguments={})],
                finish_reason="tool_calls"),
            ModelResponse(content="Built a cube."),
        ])

        result = loop.run("Create a cube")

        self.assertFalse(result.rolled_back)
        self.assertEqual(result.stopped_reason, "stop")
        self.assertIsNotNone(bridge.get_object("Cube2"))  # NOT rolled back
        self.assertIn("Built a cube.", result.reply_text)
        self.assertIn("Gemini ka quota khatam ho gaya hai", result.reply_text)
        self.assertNotIn("violations", result.reply_text)

    def test_vision_is_not_retried_after_quota(self):
        loop, bridge, _ = self._loop([
            ModelResponse(tool_calls=[ToolCall(tool_name="vision.observe", arguments={})], finish_reason="tool_calls"),
            ModelResponse(tool_calls=[ToolCall(tool_name="vision.observe", arguments={"x": 1})], finish_reason="tool_calls"),
            ModelResponse(content="Done."),
        ])
        result = loop.run("Create a cube")
        self.assertEqual(QuotaVisionTool.calls, 1)  # second call was skipped, no extra API request wasted
        self.assertFalse(result.rolled_back)
        self.assertIn("quota", result.reply_text.lower())


class TestControllerQuotaError(unittest.TestCase):

    def test_provider_quota_exception_becomes_friendly_result(self):
        from blender_ai_agent.copilot.controller import CopilotController
        from .test_copilot_controller import FakeAgent

        class QuotaAgent(FakeAgent):
            def run(self, user_input, state=None):
                raise RuntimeError(GEMINI_DAILY_429)

        controller = CopilotController(QuotaAgent(results=[]))
        result = controller.submit("make a cube")

        self.assertFalse(result.success)
        self.assertIn("Gemini ka quota khatam ho gaya hai", result.reply_text)
        self.assertNotIn("violations", result.reply_text)

    def test_other_exceptions_still_propagate(self):
        from blender_ai_agent.copilot.controller import CopilotController
        from .test_copilot_controller import FakeAgent

        class BrokenAgent(FakeAgent):
            def run(self, user_input, state=None):
                raise RuntimeError("something else broke")

        with self.assertRaises(RuntimeError):
            CopilotController(BrokenAgent(results=[])).submit("make a cube")


if __name__ == "__main__":
    unittest.main()