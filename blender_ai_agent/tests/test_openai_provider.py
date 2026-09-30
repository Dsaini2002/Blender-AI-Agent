from . import _bpy_stub  # noqa: F401

import json
import unittest
from unittest.mock import MagicMock, patch

from blender_ai_agent.providers.openai_provider import OpenAIProvider


class _FakeHTTPResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestOpenAIProviderDefaults(unittest.TestCase):

    def test_default_model_is_gpt6_astra(self):
        provider = OpenAIProvider(api_key="sk-test")
        self.assertEqual(provider._model_name, "gpt-6-astra")

    def test_endpoint_is_openai_chat_completions(self):
        self.assertEqual(
            OpenAIProvider.API_URL, "https://api.openai.com/v1/chat/completions"
        )

    def test_custom_model_name_honored(self):
        provider = OpenAIProvider(api_key="sk-test", model_name="gpt-6-astra-pro")
        self.assertEqual(provider._model_name, "gpt-6-astra-pro")


class TestOpenAIProviderRequestResponse(unittest.TestCase):

    @patch("blender_ai_agent.providers.openai_provider.urllib.request.urlopen")
    def test_generate_parses_text_response(self, mock_urlopen):
        mock_urlopen.return_value = _FakeHTTPResponse({
            "choices": [{"message": {"content": "Done.", "tool_calls": []}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })
        provider = OpenAIProvider(api_key="sk-test")
        req = MagicMock(messages=[], tools=[])
        result = provider.generate(req)
        self.assertEqual(result.content, "Done.")
        self.assertEqual(result.finish_reason, "stop")

    @patch("blender_ai_agent.providers.openai_provider.urllib.request.urlopen")
    def test_generate_parses_tool_calls(self, mock_urlopen):
        mock_urlopen.return_value = _FakeHTTPResponse({
            "choices": [{"message": {
                "content": None,
                "tool_calls": [{"function": {
                    "name": "object.create",
                    "arguments": json.dumps({"name": "car_body", "primitive": "CUBE"}),
                }}],
            }}],
            "usage": {},
        })
        provider = OpenAIProvider(api_key="sk-test")
        req = MagicMock(messages=[], tools=[])
        result = provider.generate(req)
        self.assertEqual(result.finish_reason, "tool_calls")
        self.assertEqual(result.tool_calls[0].tool_name, "object.create")
        self.assertEqual(result.tool_calls[0].arguments["name"], "car_body")

    def test_request_carries_bearer_auth_header(self):
        provider = OpenAIProvider(api_key="sk-secret123")
        with patch("blender_ai_agent.providers.openai_provider.urllib.request.Request") as mock_req:
            mock_req.return_value = MagicMock()
            with patch("blender_ai_agent.providers.openai_provider.urllib.request.urlopen",
                       return_value=_FakeHTTPResponse({"choices": [{"message": {"content": "ok"}}]})):
                provider.generate(MagicMock(messages=[], tools=[]))
            _, kwargs = mock_req.call_args
            self.assertEqual(kwargs["headers"]["Authorization"], "Bearer sk-secret123")


if __name__ == "__main__":
    unittest.main()