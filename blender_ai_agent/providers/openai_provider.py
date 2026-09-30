"""
OpenAIProvider — GPT-6 Astra (and other OpenAI models)
===================================================================
Hinglish: GroqProvider jaisa hi ModelProvider implementation - Groq
ka endpoint OpenAI-compatible hai, isliye request/response shape
copy-paste jitna hi milta-julta hai. Bas API_URL aur default model
badalte hain. Koi extra pip package nahi - stdlib urllib se hi
REST call hoti hai.

Default model: "gpt-6-astra" (OpenAI's flagship model, per
api.openai.com/v1/chat/completions - see openai/gpt-6-astra in
their docs). Requires the user's OWN OPENAI_API_KEY env var - Astra
is a paid model, koi free tier nahi hai jaisa Groq ka tha.
"""

import json
import re
import time
import urllib.error
import urllib.request

from .base import ModelProvider
from ..agent.models import ModelResponse, ToolCall, Usage


class OpenAIProvider(ModelProvider):

    API_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model_name: str = "gpt-6-astra"):
        self._api_key = api_key
        self._model_name = model_name

    def generate(self, request) -> ModelResponse:
        payload = {
            "model": self._model_name,
            "messages": self._build_messages(request.messages),
            "max_completion_tokens": 1024,
        }

        tools = self._build_tools(request.tools)
        if tools:
            payload["tools"] = tools

        body = self._call_api(payload)
        return self._parse_response(body)

    # ---------------------------------------------------------
    # Private helpers (GroqProvider ke saath identical pattern)
    # ---------------------------------------------------------
    def _call_api(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )

        max_retries = 3
        for attempt in range(max_retries + 1):
            attempt_start = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    elapsed = time.perf_counter() - attempt_start
                    print(f"[TIMING]     OpenAI HTTP attempt {attempt + 1}: {elapsed:.2f}s (ok)")
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                elapsed = time.perf_counter() - attempt_start
                error_body = exc.read().decode("utf-8", errors="ignore")
                if exc.code == 429 and attempt < max_retries:
                    wait_seconds = self._parse_retry_delay(error_body)
                    print(f"[TIMING]     OpenAI HTTP attempt {attempt + 1}: {elapsed:.2f}s "
                          f"-> 429, sleeping {wait_seconds:.2f}s before retry")
                    time.sleep(wait_seconds)
                    continue
                print(f"[TIMING]     OpenAI HTTP attempt {attempt + 1}: {elapsed:.2f}s -> error {exc.code}")
                raise RuntimeError(f"OpenAI API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                elapsed = time.perf_counter() - attempt_start
                print(f"[TIMING]     OpenAI HTTP attempt {attempt + 1}: {elapsed:.2f}s -> URLError {exc.reason}")
                raise RuntimeError(f"OpenAI API request failed: {exc.reason}") from exc

    @staticmethod
    def _parse_retry_delay(error_body: str, default: float = 3.0) -> float:
        match = re.search(r"try again in ([\d.]+)s", error_body)
        if match:
            try:
                return float(match.group(1)) + 0.5
            except ValueError:
                pass
        return default

    def _build_messages(self, messages):
        built = []
        for msg in messages:
            role = msg.role
            content = msg.content
            if role == "tool":
                role = "user"
                content = f"[Tool result] {content}"
            built.append({"role": role, "content": content})
        return built

    def _build_tools(self, tool_definitions):
        if not tool_definitions:
            return []

        return [
            {
                "type": "function",
                "function": {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "parameters": tool_def.parameters or {"type": "object", "properties": {}},
                },
            }
            for tool_def in tool_definitions
        ]

    def _parse_response(self, body: dict) -> ModelResponse:
        try:
            choice = body["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected OpenAI response shape: {body}") from exc

        tool_calls = []
        for tc in message.get("tool_calls") or []:
            func = tc.get("function", {})
            raw_arguments = func.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(tool_name=func.get("name", ""), arguments=arguments))

        content = message.get("content")

        usage_data = body.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
        )

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=usage,
        )