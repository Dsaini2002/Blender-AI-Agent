from . import _bpy_stub  # noqa: F401

import json
import unittest
from unittest.mock import MagicMock, patch

from blender_ai_agent.providers.groq_provider import GroqProvider


class _FakeHTTPError(Exception):
    def __init__(self, code, body):
        self.code = code
        self._body = body.encode("utf-8")

    def read(self):
        return self._body


class _FakeHTTPResponse:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestGroqProvider413Handling(unittest.TestCase):
    """Hinglish: Groq ka free-tier TPM limit chhota hai (8000). Bada system
    prompt + lambi conversation history 413 de sakti hai - 429 ki tarah
    retry karne se fayda nahi (same size phir reject hoga), isliye
    history trim karke ek baar retry karna chahiye."""

    def _messages(self, n):
        return [{"role": "user", "content": f"msg {i}"} for i in range(n)]

    @patch("blender_ai_agent.providers.groq_provider.urllib.request.urlopen")
    def test_413_trims_history_and_retries_once(self, mock_urlopen):
        import urllib.error

        big_body = "Request too large for model... Limit 8000, Requested 9621"

        call_count = {"n": 0}

        def side_effect(req, timeout=60):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise urllib.error.HTTPError(
                    "url", 413, "too large", {}, MagicMock(read=lambda: big_body.encode())
                )
            return _FakeHTTPResponse({"choices": [{"message": {"content": "ok", "tool_calls": []}}]})

        mock_urlopen.side_effect = side_effect

        provider = GroqProvider(api_key="gsk-test")
        req = MagicMock(messages=[], tools=[])
        # 20 fake messages simulated via monkeypatching _build_messages
        provider._build_messages = lambda msgs: self._messages(20)

        result = provider.generate(req)
        self.assertEqual(result.content, "ok")
        self.assertEqual(call_count["n"], 2)  # first 413, then retried once

    @patch("blender_ai_agent.providers.groq_provider.urllib.request.urlopen")
    def test_413_still_too_large_after_trim_raises_clear_error(self, mock_urlopen):
        import urllib.error

        big_body = "Request too large..."

        def side_effect(req, timeout=60):
            raise urllib.error.HTTPError(
                "url", 413, "too large", {}, MagicMock(read=lambda: big_body.encode())
            )

        mock_urlopen.side_effect = side_effect

        provider = GroqProvider(api_key="gsk-test")
        req = MagicMock(messages=[], tools=[])
        provider._build_messages = lambda msgs: self._messages(20)

        with self.assertRaises(RuntimeError) as ctx:
            provider.generate(req)
        self.assertIn("413", str(ctx.exception))
        self.assertIn("Gemini", str(ctx.exception))

    @patch("blender_ai_agent.providers.groq_provider.urllib.request.urlopen")
    def test_429_still_retries_with_wait_not_trim(self, mock_urlopen):
        import urllib.error

        call_count = {"n": 0}

        def side_effect(req, timeout=60):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise urllib.error.HTTPError(
                    "url", 429, "rate limited", {},
                    MagicMock(read=lambda: b"try again in 0.01s"),
                )
            return _FakeHTTPResponse({"choices": [{"message": {"content": "ok", "tool_calls": []}}]})

        mock_urlopen.side_effect = side_effect

        provider = GroqProvider(api_key="gsk-test")
        req = MagicMock(messages=[], tools=[])
        provider._build_messages = lambda msgs: self._messages(3)

        result = provider.generate(req)
        self.assertEqual(result.content, "ok")


if __name__ == "__main__":
    unittest.main()