"""OpenAIProvider — GPT-6 Astra (and other OpenAI models)"""

import json
import re
import time
import urllib.error
import urllib.request
from .. import net as _net

from .base import MAX_RETRY_WAIT_S, ModelProvider, _count_vision, _meter, portable_schema, retry_wait
from ..agent.models import ModelResponse, ToolCall, Usage
from ..observability.debug import debug


class OpenAIProvider(ModelProvider):
    """OpenAI through the RESPONSES API (POST /v1/responses).

    GPT-6 Astra calls function tools only on the Responses API - on Chat Completions a request with tools is refused,
    so the agent could never build anything and the tokens were lost. It also takes no temperature, and every
    request carries reasoning tokens: reasoning effort 'low' keeps the agent's many small steps cheap."""

    API_URL = "https://api.openai.com/v1/responses"
    MAX_OUTPUT_TOKENS = 16000              # reasoning happens inside this budget: 1024 cut answers off
    REASONING_EFFORT = "low"               # low / medium / high / xhigh / max ('none' and 'minimal' are refused)
    TIMEOUT_S = 180

    def __init__(self, api_key: str, model_name: str = "gpt-6-sol"):
        self._api_key = api_key
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(self, request) -> ModelResponse:
        instructions, items = self._build_input(request.messages)
        payload = {
            "model": self._model_name,
            "input": items,
            "max_output_tokens": self.MAX_OUTPUT_TOKENS,
            "reasoning": {"effort": self.REASONING_EFFORT},
            "store": False,
        }
        if instructions:
            payload["instructions"] = instructions
        tools = self._build_tools(request.tools)
        if tools:
            payload["tools"] = tools
        body = self._call_api(payload)
        return _meter("openai", self._model_name, self._parse_response(body))

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
                with _net.urlopen(req, timeout=self.TIMEOUT_S) as resp:
                    elapsed = time.perf_counter() - attempt_start
                    debug(f"[TIMING]     OpenAI HTTP attempt {attempt + 1}: {elapsed:.2f}s (ok)")
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                elapsed = time.perf_counter() - attempt_start
                error_body = exc.read().decode("utf-8", errors="ignore")
                if exc.code in (500, 502, 503, 504) and attempt < max_retries:
                    retry_wait(min(MAX_RETRY_WAIT_S, 2.0 * (attempt + 1) ** 2), "OpenAI")   # busy: 2, 8, 18 s
                    continue
                if exc.code == 429 and attempt < max_retries and "insufficient_quota" not in error_body:
                    wait_seconds = self._parse_retry_delay(error_body)
                    debug(f"[TIMING]     OpenAI HTTP attempt {attempt + 1}: {elapsed:.2f}s "
                          f"-> 429, sleeping {wait_seconds:.2f}s before retry")
                    retry_wait(wait_seconds, "OpenAI")
                    continue
                debug(f"[TIMING]     OpenAI HTTP attempt {attempt + 1}: {elapsed:.2f}s -> error {exc.code}")
                raise RuntimeError(f"OpenAI API error {exc.code}: {error_body}") from exc
            except urllib.error.URLError as exc:
                elapsed = time.perf_counter() - attempt_start
                debug(f"[TIMING]     OpenAI HTTP attempt {attempt + 1}: {elapsed:.2f}s -> URLError {exc.reason}")
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

    @staticmethod
    def _build_input(messages):
        """Our conversation -> (instructions, input items). System texts become the instructions; tool results are
        plain user text (no call ids are kept between turns)."""
        system, items = [], []
        for msg in messages:
            content = msg.content or ""
            if msg.role == "system":
                if content:
                    system.append(content)
                continue
            role = msg.role
            if role == "tool":
                role, content = "user", f"[Tool result] {content}"
            if not content:
                continue
            items.append({"role": "assistant" if role == "assistant" else "user", "content": content})
        if not items:
            items.append({"role": "user", "content": "(continue)"})
        return "\n\n".join(system), items

    # kept for older callers / tests
    def _build_messages(self, messages):
        instructions, items = self._build_input(messages)
        return ([{"role": "system", "content": instructions}] if instructions else []) + items

    def _build_tools(self, tool_definitions):
        # function names allow only [a-zA-Z0-9_-]: 'object.create' is sent as 'object__create' and mapped back
        from .claude_provider import to_claude_name
        self._names = {to_claude_name(d.name): d.name for d in (tool_definitions or [])}
        return [
            {
                "type": "function",
                "name": to_claude_name(tool_def.name),
                "description": (tool_def.description or tool_def.name)[:4000],
                "parameters": portable_schema(tool_def.parameters or {"type": "object", "properties": {}}, top=True),
            }
            for tool_def in tool_definitions or []
        ]

    def _parse_response(self, body: dict) -> ModelResponse:
        from .claude_provider import from_claude_name
        if not isinstance(body, dict) or ("output" not in body and "error" in body):
            raise RuntimeError(f"Unexpected OpenAI response: {str(body)[:400]}")
        tool_calls, texts = [], []
        for item in body.get("output") or []:
            kind = item.get("type")
            if kind == "function_call":
                try:
                    arguments = json.loads(item.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}
                tool_calls.append(ToolCall(tool_name=from_claude_name(item.get("name", ""), getattr(self, "_names", None)),
                                           arguments=arguments if isinstance(arguments, dict) else {}))
            elif kind == "message":
                for part in item.get("content") or []:
                    if part.get("type") in ("output_text", "text") and part.get("text"):
                        texts.append(part["text"])
        if not texts and body.get("output_text"):
            texts.append(str(body["output_text"]))
        usage_data = body.get("usage") or {}
        usage = Usage(prompt_tokens=usage_data.get("input_tokens", usage_data.get("prompt_tokens", 0)),
                      completion_tokens=usage_data.get("output_tokens", usage_data.get("completion_tokens", 0)))
        reasoning = (usage_data.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
        if reasoning:
            try:
                from ..observability import run_trace
                run_trace.note(f"AI     (OpenAI reasoning: {reasoning:,} of the {usage.completion_tokens:,} output tokens)")
            except Exception:  # noqa: BLE001
                pass
        incomplete = body.get("status") == "incomplete"
        if incomplete and not tool_calls and not texts:
            reason = (body.get("incomplete_details") or {}).get("reason", "")
            # all the budget went into thinking: say so instead of 'doing nothing' silently
            raise RuntimeError(f"OpenAI stopped before answering ({reason or 'incomplete'}): it used "
                               f"{usage.completion_tokens:,} output tokens ({reasoning:,} reasoning) and wrote no step.")
        return ModelResponse(
            content="\n".join(texts) or None,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else ("length" if incomplete else "stop"),
            usage=usage,
        )


class OpenAIVisionClient:
    """generate(system, parts, ...) like self_correct.GeminiClient, answered by OpenAI - so the automatic check looks
    at the renders with the OpenAI model picked in the panel."""

    DEFAULT_MODEL = "gpt-6-astra"

    def __init__(self, cfg):
        self.cfg = cfg
        self.model = getattr(cfg, "vision_model", "") or self.DEFAULT_MODEL

    def models(self):
        return [self.model]

    def generate(self, system: str, parts, json_mode: bool = False, temperature: float = 0.4,
                 max_output_tokens: int = 8000) -> str:
        from ..agent.self_correct import BuilderError

        if not self.cfg.api_key:
            raise BuilderError("no key", "OpenAI API key not found.")
        content = []
        for part in parts or []:
            if part.get("text"):
                content.append({"type": "input_text", "text": part["text"]})
            elif part.get("inline_data"):
                inline = part["inline_data"]
                content.append({"type": "input_image",
                                "image_url": f"data:{inline.get('mime_type', 'image/png')};base64,{inline.get('data', '')}"})
        payload = {"model": self.model, "instructions": system, "store": False,
                   "max_output_tokens": max(4000, min(int(max_output_tokens) * 2, 32000)),
                   "reasoning": {"effort": "low"},
                   "input": [{"role": "user", "content": content or [{"type": "input_text", "text": "(no input)"}]}]}
        if json_mode:
            payload["text"] = {"format": {"type": "json_object"}}
        timeout = min(float(getattr(self.cfg, "request_timeout_s", 120.0) or 120.0), 300.0)
        req = urllib.request.Request(OpenAIProvider.API_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.cfg.api_key}"})
        try:
            with _net.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", "replace")
            raise BuilderError(f"openai {exc.code}: {text[:400]}", f"OpenAI error {exc.code}: {text[:200]}") from exc
        except urllib.error.URLError as exc:
            raise BuilderError(f"cannot reach OpenAI: {exc.reason}", f"Could not connect to OpenAI ({exc.reason}).") from exc
        except (TimeoutError, OSError) as exc:
            raise BuilderError("timeout", f"OpenAI did not answer within {timeout:.0f}s.") from exc
        usage = body.get("usage") or {}
        _count_vision("openai", self.model, usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        text = "".join(part.get("text", "") for item in body.get("output") or [] if item.get("type") == "message"
                       for part in item.get("content") or [] if part.get("type") in ("output_text", "text"))
        text = text or str(body.get("output_text") or "")
        if not text.strip():
            raise BuilderError("empty reply", "OpenAI returned an empty answer.")
        return text
