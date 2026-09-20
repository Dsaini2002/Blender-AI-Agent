"""
GeminiProvider — Real LLM Provider
=======================================
Hinglish: Phase 3 ka ModelProvider abstraction implement karta hai
Google Gemini ke saath. Isse Agent ko koi fark nahi padta — same
interface jo MockProvider follow karta hai.

PATCHED (rate-limit resilience): GroqProvider ki tarah, ab Gemini bhi
429 (rate limit) errors par khud retry karta hai, taaki free-tier ka
"5 requests/minute" jaisa strict limit user ko error dikhake task
BEECH mein na rok de — thodi der wait karke khud-ba-khud continue ho
jaata hai (jab tak retries khatam na ho jaayein).
"""

import json
import re
import time

from .base import ModelProvider
from ..agent.models import ModelResponse, ToolCall, Usage


class RateLimited(Exception):
    """429 aaya aur wait bahut lamba hai (ya quota 0 hai) - fallback model try karo."""

    def __init__(self, wait_seconds: float, message: str = ""):
        super().__init__(message or f"rate limited, retry in {wait_seconds:.1f}s")
        self.wait_seconds = wait_seconds


class GeminiProvider(ModelProvider):

    # Free tier par lamba wait (55-60s) karne ki jagah is se lamba delay aaye
    # to turant agle model par switch karte hain.
    MAX_INLINE_WAIT_SECONDS = 15.0
    DEFAULT_FALLBACK_MODELS = ("gemini-3.6-flash", "gemini-3.5-flash-lite")

    def __init__(self, api_key: str, model_name: str = "gemini-3.6-flash", fallback_models=None):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model_name
        candidates = self.DEFAULT_FALLBACK_MODELS if fallback_models is None else fallback_models
        self._fallback_models = [m for m in candidates if m != model_name]

    def generate(self, request) -> ModelResponse:
        tools = self._build_tools(request.tools)
        contents = self._build_contents(request.messages)

        models_to_try = [self._model_name] + self._fallback_models
        for index, name in enumerate(models_to_try):
            is_last = index == len(models_to_try) - 1
            model = self._genai.GenerativeModel(
                model_name=name,
                tools=tools if tools else None,
            )
            try:
                response = self._generate_with_retry(
                    model, contents,
                    max_inline_wait=None if is_last else self.MAX_INLINE_WAIT_SECONDS,
                )
            except RateLimited as exc:
                print(f"[TIMING]     {name} rate-limited (retry {exc.wait_seconds:.0f}s) "
                      f"-> switching to {models_to_try[index + 1]}")
                continue

            if name != self._model_name:
                print(f"[TIMING]     Now using fallback model: {name}")
                self._model_name = name   # sticky: har turn pe dobara 429 na khaye
                self._fallback_models = [m for m in models_to_try if m != name]
            return self._parse_response(response)

        raise RuntimeError("All Gemini models are rate limited.")  # pragma: no cover

    def _generate_with_retry(self, model, contents, max_inline_wait=None):
        """
        Hinglish: Gemini free tier ka "requests per minute" quota bahut
        tight hota hai (jaise 5/min ya 15/min). Jab wo hit ho jaata hai,
        Google 429 error deta hai jisme WOH KHUD bata deta hai "retry
        in N seconds" — hum usi N ko parse karke utna wait karte hain,
        phir dobara try karte hain, GroqProvider ke _call_api() jaisa
        hi pattern.
        """
        max_retries = 3
        for attempt in range(max_retries + 1):
            attempt_start = time.perf_counter()
            try:
                response = model.generate_content(contents)
                elapsed = time.perf_counter() - attempt_start
                print(f"[TIMING]     Gemini attempt {attempt + 1}: {elapsed:.2f}s (ok)")
                return response
            except Exception as exc:  # noqa: BLE001 — SDK ka exact exception type
                # version ke hisaab se badal sakta hai, isliye message
                # ke content pe hi rely karte hain.
                elapsed = time.perf_counter() - attempt_start
                message = str(exc)
                if "429" in message and attempt < max_retries:
                    wait_seconds = self._parse_retry_delay(message)
                    quota_zero = "limit: 0" in message
                    if max_inline_wait is not None and (quota_zero or wait_seconds > max_inline_wait):
                        raise RateLimited(wait_seconds, message) from exc
                    print(f"[TIMING]     Gemini attempt {attempt + 1}: {elapsed:.2f}s "
                          f"-> 429, sleeping {wait_seconds:.2f}s before retry")
                    time.sleep(wait_seconds)
                    continue
                print(f"[TIMING]     Gemini attempt {attempt + 1}: {elapsed:.2f}s -> error")
                raise

    @staticmethod
    def _parse_retry_delay(error_message: str, default: float = 5.0) -> float:
        """
        Hinglish: Gemini ka error message ("Please retry in
        31.334966899s.") ya uska structured 'retry_delay { seconds: N }'
        block — dono se exact wait time nikal lete hain, guess karne
        ki jagah. Thoda buffer (+0.5s) add karte hain taaki clock-skew
        se dubara turant 429 na aaye.
        """
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
                "parameters": tool_def.parameters or {"type": "object", "properties": {}},
            })

        return [{"function_declarations": function_declarations}]

    def _build_contents(self, messages):
        """Hinglish: Humare Message list ko Gemini ke 'contents' format mein badalta hai."""
        contents = []
        for msg in messages:
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        return contents

    def _parse_response(self, response) -> ModelResponse:
        tool_calls = []
        text_content = None

        try:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                    fc = part.function_call
                    arguments = dict(fc.args) if fc.args else {}
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