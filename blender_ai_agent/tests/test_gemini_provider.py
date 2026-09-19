from . import _bpy_stub  # noqa: F401

import unittest
from unittest.mock import patch

from blender_ai_agent.providers.gemini_provider import GeminiProvider


def make_provider():
    """Hinglish: google.generativeai package sandbox mein installed
    nahi hai (aur na hone ki zaroorat hai) — isliye __init__() (jo
    genai.configure() karta hai) ko skip karke seedha object banate
    hain. Humein sirf _generate_with_retry() aur _parse_retry_delay()
    test karne hain, jo genai instance use nahi karte."""
    return object.__new__(GeminiProvider)


class FakeModel:
    """Hinglish: google.generativeai ka GenerativeModel jaisa fake —
    generate_content() ko N baar 429 se fail karwate hain, fir success."""

    def __init__(self, fail_times, error_message):
        self.fail_times = fail_times
        self.error_message = error_message
        self.calls = 0

    def generate_content(self, contents):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError(self.error_message)
        return "FAKE_RESPONSE"


class TestGeminiProviderRetry(unittest.TestCase):

    def test_parses_retry_delay_from_gemini_error_message(self):
        provider = make_provider()
        delay = provider._parse_retry_delay(
            "Unexpected error: 429 ... Please retry in 31.334966899s. [links {...}]"
        )
        self.assertAlmostEqual(delay, 31.834966899, places=3)

    def test_parses_retry_delay_from_structured_seconds_block(self):
        provider = make_provider()
        delay = provider._parse_retry_delay("... retry_delay {\n  seconds: 51\n}")
        self.assertAlmostEqual(delay, 51.5, places=3)

    def test_falls_back_to_default_when_no_delay_found(self):
        provider = make_provider()
        delay = provider._parse_retry_delay("some totally different error")
        self.assertEqual(delay, 5.0)

    @patch("time.sleep", return_value=None)
    def test_retries_once_on_429_then_succeeds(self, mock_sleep):
        provider = make_provider()
        model = FakeModel(fail_times=1, error_message="429 Please retry in 2.0s.")

        result = provider._generate_with_retry(model, contents=[])

        self.assertEqual(result, "FAKE_RESPONSE")
        self.assertEqual(model.calls, 2)
        mock_sleep.assert_called_once()

    @patch("time.sleep", return_value=None)
    def test_gives_up_after_max_retries_and_raises(self, mock_sleep):
        provider = make_provider()
        model = FakeModel(fail_times=10, error_message="429 Please retry in 1.0s.")

        with self.assertRaises(RuntimeError):
            provider._generate_with_retry(model, contents=[])

        # max_retries=3 -> 4 total attempts (1 original + 3 retries)
        self.assertEqual(model.calls, 4)

    @patch("time.sleep", return_value=None)
    def test_non_429_error_raises_immediately_without_retry(self, mock_sleep):
        provider = make_provider()
        model = FakeModel(fail_times=1, error_message="500 Internal Server Error")

        with self.assertRaises(RuntimeError):
            provider._generate_with_retry(model, contents=[])

        self.assertEqual(model.calls, 1)
        mock_sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()