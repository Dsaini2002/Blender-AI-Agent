from . import _bpy_stub  # noqa: F401

import unittest
from unittest.mock import MagicMock, mock_open, patch

from blender_ai_agent.vision.providers.gemini_vision_provider import GeminiVisionProvider


class TestGeminiVisionProviderParsing(unittest.TestCase):

    def test_valid_json_response_parses_into_observation(self):
        text = '{"description": "A red car", "objects_detected": ["car_body", "car_wheel_fl"], "issues": [], "confidence": 0.9}'
        obs = GeminiVisionProvider._parse_response(text)
        self.assertEqual(obs.description, "A red car")
        self.assertIn("car_body", obs.objects_detected)
        self.assertEqual(obs.issues, [])
        self.assertAlmostEqual(obs.confidence, 0.9)

    def test_markdown_fenced_json_is_stripped(self):
        text = '```json\n{"description": "ok", "confidence": 0.8}\n```'
        obs = GeminiVisionProvider._parse_response(text)
        self.assertEqual(obs.description, "ok")

    def test_issues_are_surfaced(self):
        text = '{"description": "car", "issues": ["left wheel is floating above the ground"], "confidence": 0.7}'
        obs = GeminiVisionProvider._parse_response(text)
        self.assertIn("left wheel is floating above the ground", obs.issues)

    def test_unparseable_text_becomes_low_confidence_observation_not_crash(self):
        obs = GeminiVisionProvider._parse_response("I cannot help with that.")
        self.assertLess(obs.confidence, 0.5)
        self.assertTrue(obs.is_low_confidence)

    def test_confidence_out_of_range_is_clamped(self):
        text = '{"description": "x", "confidence": 5.0}'
        obs = GeminiVisionProvider._parse_response(text)
        self.assertEqual(obs.confidence, 1.0)

    def test_empty_text_does_not_crash(self):
        obs = GeminiVisionProvider._parse_response("")
        self.assertTrue(obs.is_low_confidence)


class TestGeminiVisionProviderAnalyze(unittest.TestCase):

    def test_analyze_sends_image_bytes_and_returns_observation(self):
        provider = object.__new__(GeminiVisionProvider)
        fake_genai = MagicMock()
        fake_response = MagicMock()
        fake_response.text = '{"description": "a car", "confidence": 0.85}'
        fake_genai.GenerativeModel.return_value.generate_content.return_value = fake_response
        provider._genai = fake_genai
        provider._model_name = "gemini-3.6-flash"

        with patch("builtins.open", mock_open(read_data=b"\\x89PNG...")):
            obs = provider.analyze("/tmp/preview.png", {})

        self.assertEqual(obs.description, "a car")
        call_args = fake_genai.GenerativeModel.return_value.generate_content.call_args[0][0]
        self.assertEqual(call_args[1]["mime_type"], "image/png")


if __name__ == "__main__":
    unittest.main()