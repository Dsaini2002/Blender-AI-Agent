"""15 Nov: Groq picked, but the error said 'Gemini requests/minute limit ... ~43745 seconds'. Groq's free plan allows
8,000 tokens per minute; one agent step is ~18,000 -> 413 'Request too large' -> switched to Gemini -> Gemini's daily
quota was used up -> only Gemini's error was shown (and called a per-minute limit)."""

from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability import friendly_errors as fe

GROQ_413 = ('Groq API error 413: {"error":{"message":"Request too large for model `openai/gpt-oss-120b` in organization '
            'org_x service tier `on_demand` on tokens per minute (TPM): Limit 8000, Requested 18167, please reduce your '
            'message size and try again.","type":"tokens","code":"rate_limit_exceeded"}}')
GEMINI_DAY = ('Gemini API error 429: RESOURCE_EXHAUSTED quota exceeded for metric generativelanguage.googleapis.com/'
              'generate_content_free_tier_requests, limit: 20, model: gemini-3.6-flash. Please retry in 43744.2s.')


class GroqTooLargeTest(unittest.TestCase):

    def test_groq_413_is_explained_not_called_a_quota(self):
        self.assertEqual(fe.too_large_for_plan(GROQ_413), (8000, 18167))
        message = fe.friendly_error_message(GROQ_413)
        self.assertTrue(message.startswith("Groq's plan allows only 8,000 tokens per minute"), message)
        self.assertIn("18,167", message)
        self.assertIn("Waiting does not help", message)

    def test_a_normal_rate_limit_is_not_too_large(self):
        self.assertIsNone(fe.too_large_for_plan("429 Rate limit reached on tokens per minute (TPM): Limit 8000, "
                                                "Used 7000, Requested 900. Please try again in 7s"))

    def test_hours_long_wait_is_said_in_hours(self):
        message = fe.friendly_error_message(GEMINI_DAY)
        self.assertIn("Gemini quota is used up", message)
        self.assertIn("~12 h", message)
        self.assertNotIn("43745 seconds", message)

    def test_both_failures_are_shown_groq_first(self):
        message = fe.providers_failed_message([("groq", GROQ_413), ("gemini", GEMINI_DAY)])
        self.assertTrue(message.startswith("Groq failed: Groq's plan allows only 8,000"), message)
        self.assertIn("Then tried Gemini instead: Gemini quota is used up", message)



if __name__ == "__main__":
    unittest.main()
