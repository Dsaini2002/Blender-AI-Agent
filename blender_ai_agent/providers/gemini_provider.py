"""GeminiProvider — Real LLM Provider"""

import json
import re
import time

from .base import MAX_RETRY_WAIT_S, ModelProvider, _meter, portable_schema, retry_wait
from ..agent.models import ModelResponse, ToolCall, Usage
from ..tools.models import to_plain
from ..observability.debug import debug


class RateLimited(Exception):

    def __init__(self, wait_seconds: float, message: str = ""):
        super().__init__(message or f"rate limited, retry in {wait_seconds:.1f}s")
        self.wait_seconds = wait_seconds


class RestGeminiModel:
    """generate_content() over the Gemini REST API - the same contents / tools dicts the SDK takes."""

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"
    TIMEOUT_S = 120.0

    def __init__(self, api_key: str, model_name: str, tools=None):
        self.api_key, self.model_name, self.tools = api_key, model_name, tools or []

    def generate_content(self, contents):
        import urllib.error
        import urllib.request

        from .. import net

        payload = {"contents": contents}
        if self.tools:
            payload["tools"] = self.tools
        request = urllib.request.Request(
            f"{self.API_BASE}/models/{self.model_name}:generateContent", data=json.dumps(payload).encode("utf-8"),
            method="POST", headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
        try:
            with net.urlopen(request, timeout=self.TIMEOUT_S) as response:
                return json.loads(response.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            try:
                error = (json.loads(body).get("error") or {})
            except ValueError:
                error = {}
            message = error.get("message") or body[:300]
            delay = ""
            for detail in error.get("details") or []:
                if isinstance(detail, dict) and detail.get("retryDelay"):
                    delay = f" Please retry in {str(detail['retryDelay']).rstrip('s')}s."
            # keep the SDK's wording ("429 ... retry in Xs") so the retry and quota handling work the same
            raise RuntimeError(f"{exc.code} {message}{delay}") from exc


class GeminiProvider(ModelProvider):

    MAX_INLINE_WAIT_SECONDS = 15.0
    TIMEOUT_S = 120.0
    DEFAULT_FALLBACK_MODELS = ("gemini-3.6-flash", "gemini-3.5-flash-lite")

    def __init__(self, api_key: str, model_name: str = "gemini-3.6-flash", fallback_models=None):
        # The google-generativeai package is not part of Blender's Python. Without it, the same requests go
        # straight to the REST API (urllib), so a fresh Blender + the add-on zip works with no installs.
        self._api_key = api_key
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._genai = genai
        except ImportError:
            self._genai = None
        self._model_name = model_name
        candidates = self.DEFAULT_FALLBACK_MODELS if fallback_models is None else fallback_models
        self._fallback_models = [m for m in candidates if m != model_name]

    def generate(self, request) -> ModelResponse:
        tools = self._build_tools(request.tools)
        contents = self._build_contents(request.messages)

        models_to_try = [self._model_name] + self._fallback_models
        for index, name in enumerate(models_to_try):
            is_last = index == len(models_to_try) - 1
            if getattr(self, "_genai", None) is not None:
                model = self._genai.GenerativeModel(
                    model_name=name,
                    tools=tools if tools else None,
                )
            else:
                model = RestGeminiModel(getattr(self, "_api_key", ""), name, tools)
            try:
                response = self._generate_with_retry(
                    model, contents,
                    max_inline_wait=None if is_last else self.MAX_INLINE_WAIT_SECONDS,
                )
            except RateLimited as exc:
                debug(f"[TIMING]     {name} rate-limited (retry {exc.wait_seconds:.0f}s) "
                      f"-> switching to {models_to_try[index + 1]}")
                continue

            if name != self._model_name:
                debug(f"[TIMING]     Now using fallback model: {name}")
                self._model_name = name
                self._fallback_models = [m for m in models_to_try if m != name]
            return _meter("gemini", name, self._parse_response(response))

        raise RuntimeError("All Gemini models are rate limited.")  # pragma: no cover

    def _generate_with_retry(self, model, contents, max_inline_wait=None):
        max_retries = 3
        for attempt in range(max_retries + 1):
            attempt_start = time.perf_counter()
            try:
                if isinstance(model, RestGeminiModel):
                    response = model.generate_content(contents)
                else:
                    try:                                       # the SDK has no timeout of its own: never hang
                        response = model.generate_content(contents, request_options={"timeout": self.TIMEOUT_S})
                    except TypeError:
                        response = model.generate_content(contents)
                elapsed = time.perf_counter() - attempt_start
                debug(f"[TIMING]     Gemini attempt {attempt + 1}: {elapsed:.2f}s (ok)")
                return response
            except Exception as exc:  # noqa: BLE001 
                elapsed = time.perf_counter() - attempt_start
                message = str(exc)
                if "429" in message and attempt < max_retries:
                    wait_seconds = self._parse_retry_delay(message)
                    compact = message.lower().replace(" ", "")
                    hopeless = "limit:0" in compact or "perday" in compact or wait_seconds > MAX_RETRY_WAIT_S
                    if max_inline_wait is not None and (hopeless or wait_seconds > max_inline_wait):
                        raise RateLimited(wait_seconds, message) from exc
                    if hopeless:
                        raise RuntimeError(f"429 Gemini quota is used up (retry in {wait_seconds:.0f}s). "
                                           f"{message[:300]}") from exc
                    debug(f"[TIMING]     Gemini attempt {attempt + 1}: {elapsed:.2f}s "
                          f"-> 429, sleeping {wait_seconds:.2f}s before retry")
                    retry_wait(wait_seconds, "Gemini")
                    continue
                busy = any(mark in message for mark in (" 500", " 502", " 503", " 504", "UNAVAILABLE", "overloaded",
                                                         "INTERNAL", "Deadline", "timed out"))
                if busy and attempt < max_retries:
                    retry_wait(min(MAX_RETRY_WAIT_S, 2.0 * (attempt + 1) ** 2), "Gemini")      # 2, 8, 18 s
                    continue
                debug(f"[TIMING]     Gemini attempt {attempt + 1}: {elapsed:.2f}s -> error")
                raise

    @staticmethod
    def _parse_retry_delay(error_message: str, default: float = 5.0) -> float:
        match = re.search(r"retry in ([\d.]+)s", error_message)
        if not match:
            match = re.search(r"seconds:\s*(\d+)", error_message)
        if match:
            try:
                return float(match.group(1)) + 0.5
            except ValueError:
                pass
        return default

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _build_tools(self, tool_definitions):
        if not tool_definitions:
            return []

        function_declarations = []
        for tool_def in tool_definitions:
            function_declarations.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "parameters": portable_schema(tool_def.parameters or {"type": "object", "properties": {}}, top=True),
            })

        return [{"function_declarations": function_declarations}]

    def _build_contents(self, messages):
        contents = []
        for msg in messages:
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        return contents

    def _parse_response(self, response) -> ModelResponse:
        if isinstance(response, dict):
            return self._parse_rest_response(response)
        tool_calls = []
        text_content = None

        try:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                    fc = part.function_call
                    arguments = to_plain(dict(fc.args)) if fc.args else {}
                    tool_calls.append(ToolCall(tool_name=fc.name, arguments=arguments))
                elif hasattr(part, "text") and part.text:
                    text_content = part.text
        except (IndexError, AttributeError):
            text_content = getattr(response, "text", "") or "I couldn't generate a response."

        usage = Usage()
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = Usage(
                prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", 0),
                completion_tokens=getattr(response.usage_metadata, "candidates_token_count", 0),
            )

        return ModelResponse(
            content=text_content,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=usage,
        )

    @staticmethod
    def _parse_rest_response(data: dict) -> ModelResponse:
        tool_calls, texts = [], []
        candidates = data.get("candidates") or []
        for part in ((candidates[0].get("content") or {}).get("parts") or []) if candidates else []:
            call = part.get("functionCall")
            if call and call.get("name"):
                tool_calls.append(ToolCall(tool_name=call["name"], arguments=to_plain(call.get("args") or {})))
            elif part.get("text"):
                texts.append(part["text"])
        if not candidates and not texts:
            block = (data.get("promptFeedback") or {}).get("blockReason")
            texts.append(f"Gemini blocked the request ({block})." if block else "I couldn't generate a response.")
        meta = data.get("usageMetadata") or {}
        usage = Usage(prompt_tokens=meta.get("promptTokenCount", 0), completion_tokens=meta.get("candidatesTokenCount", 0))
        return ModelResponse(content="\n".join(texts) or None, tool_calls=tool_calls,
                             finish_reason="tool_calls" if tool_calls else "stop", usage=usage)