"""ClaudeProvider - Anthropic Claude over the Messages REST API (no SDK needed).

Tool names: Claude allows only [a-zA-Z0-9_-] in tool names, so 'mesh.building' is sent as 'mesh__building' and
mapped back when Claude calls it.
"""

import json
import re
import time
import urllib.error
import urllib.request

from .. import net as _net
from ..agent.models import ModelResponse, ToolCall, Usage
from ..observability.debug import debug
from .base import MAX_RETRY_WAIT_S, ModelProvider, _count_vision, _meter, portable_schema, retry_wait

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"
MODELS = (
    ("claude-sonnet-5-5", "Claude Sonnet 5.5", "Fast and strong - best value for building scenes"),
    ("claude-opus-5-5", "Claude Opus 5.5", "Strongest reasoning for big, detailed scenes (slower, pricier)"),
    ("claude-haiku-5-5", "Claude Haiku 5.5", "Fastest and cheapest, for simple edits"),
)


def to_claude_name(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name.replace(".", "__"))[:64]


def from_claude_name(name: str, known=None) -> str:
    if known and name in known:
        return known[name]
    return name.replace("__", ".")


def claude_messages(messages):
    """Our conversation -> Claude's: system text apart, tool results as user text, roles alternating,
    starting and ending with the user."""
    system_parts, out = [], []
    for msg in messages:
        text = (msg.content or "").strip()
        if msg.role == "system":
            if text:
                system_parts.append(text)
            continue
        if not text:
            continue
        role = "assistant" if msg.role == "assistant" else "user"
        if msg.role == "tool":
            text = f"[Tool result] {text}"
        if out and out[-1]["role"] == role:
            out[-1]["content"] += "\n\n" + text
        else:
            out.append({"role": role, "content": text})
    if not out or out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": "(start)"})
    if out[-1]["role"] != "user":
        out.append({"role": "user", "content": "Continue."})
    return "\n\n".join(system_parts), out


def friendly_http_error(code: int, body: str, retry_after: str = "") -> str:
    try:
        error = (json.loads(body).get("error") or {})
    except ValueError:
        error = {}
    message = error.get("message") or body[:300]
    low = message.lower()
    if code == 401:
        return f"401 Claude API key is not valid ({message}). Paste a new key from console.anthropic.com."
    if code == 400 and ("credit" in low or "billing" in low):
        return f"402 Claude: your Anthropic credit balance is too low ({message}). Add credit at console.anthropic.com."
    if code == 429:
        wait = f" Please retry in {retry_after}s." if retry_after else ""
        return f"429 Claude rate limit / quota: {message}.{wait}"
    if code == 404 and "model" in low:
        return f"404 Claude model not found ({message}). Pick another Claude model in the panel."
    return f"Claude API error {code}: {message}"


class ClaudeProvider(ModelProvider):

    MAX_TOKENS = 16000
    TIMEOUT_S = 180.0
    RETRIES = 3

    def __init__(self, api_key: str, model_name: str = DEFAULT_MODEL, max_tokens: int = None):
        self._api_key = api_key
        self._model_name = model_name or DEFAULT_MODEL
        self._max_tokens = int(max_tokens or self.MAX_TOKENS)

    @property
    def model_name(self) -> str:
        return self._model_name

    def generate(self, request) -> ModelResponse:
        system, messages = claude_messages(request.messages)
        payload = {"model": self._model_name, "max_tokens": self._max_tokens, "messages": messages}
        if system:
            payload["system"] = system
        names = {}
        tools = []
        for tool in request.tools or []:
            claude_name = to_claude_name(tool.name)
            names[claude_name] = tool.name
            schema = portable_schema(tool.parameters or {"type": "object", "properties": {}}, top=True)
            if schema.get("type") != "object":
                schema = {"type": "object", "properties": {}}
            tools.append({"name": claude_name, "description": (tool.description or tool.name)[:4000],
                          "input_schema": schema})
        if tools:
            payload["tools"] = tools
        return _meter("claude", self._model_name, self.parse_response(self._call(payload), names))

    def _call(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        for attempt in range(self.RETRIES + 1):
            req = urllib.request.Request(API_URL, data=data, method="POST", headers={
                "x-api-key": self._api_key, "anthropic-version": API_VERSION, "content-type": "application/json"})
            started = time.perf_counter()
            try:
                with _net.urlopen(req, timeout=self.TIMEOUT_S) as resp:
                    debug(f"[TIMING]     Claude HTTP attempt {attempt + 1}: {time.perf_counter() - started:.2f}s (ok)")
                    return json.loads(resp.read().decode("utf-8", "replace") or "{}")
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")
                retry_after = (exc.headers.get("retry-after") if exc.headers else "") or ""
                if exc.code in (429, 500, 502, 503, 529) and attempt < self.RETRIES:
                    try:
                        wait = min(30.0, float(retry_after)) if retry_after else 2.0 * (attempt + 1)
                    except ValueError:
                        wait = 2.0 * (attempt + 1)
                    debug(f"[TIMING]     Claude HTTP {exc.code}, retry in {wait:.1f}s")
                    retry_wait(wait, "Claude")
                    continue
                raise RuntimeError(friendly_http_error(exc.code, body, retry_after)) from exc
            except urllib.error.URLError as exc:
                raise RuntimeError(f"Could not reach Claude (api.anthropic.com): {exc.reason}") from exc
        raise RuntimeError("Claude did not answer.")

    @staticmethod
    def parse_response(body: dict, names=None) -> ModelResponse:
        texts, calls = [], []
        for block in body.get("content") or []:
            kind = block.get("type")
            if kind == "text" and block.get("text"):
                texts.append(block["text"])
            elif kind == "tool_use" and block.get("name"):
                args = block.get("input")
                calls.append(ToolCall(tool_name=from_claude_name(block["name"], names),
                                      arguments=args if isinstance(args, dict) else {}))
        if not texts and not calls and body.get("type") == "error":
            raise RuntimeError(f"Claude API error: {(body.get('error') or {}).get('message', body)}")
        usage = body.get("usage") or {}
        return ModelResponse(content="\n".join(texts) or None, tool_calls=calls,
                             finish_reason="tool_calls" if calls else ("length" if body.get("stop_reason") == "max_tokens"
                                                                       else "stop"),
                             usage=Usage(prompt_tokens=usage.get("input_tokens", 0),
                                         completion_tokens=usage.get("output_tokens", 0)))


class ClaudeVisionClient:
    """The same generate(system, parts, ...) as self_correct.GeminiClient, answered by Claude - so the automatic
    check and build.iterate can look at renders with Claude."""

    TIMEOUT_S = 120.0

    def __init__(self, cfg):
        self.cfg = cfg
        self.model = getattr(cfg, "vision_model", "") or DEFAULT_MODEL

    def models(self):
        return [self.model]

    def generate(self, system: str, parts, json_mode: bool = False, temperature: float = 0.4,
                 max_output_tokens: int = 8000) -> str:
        from ..agent.self_correct import BuilderError

        if not self.cfg.api_key:
            raise BuilderError("no key", "Claude API key not found.")
        content = []
        for part in parts or []:
            if part.get("text"):
                content.append({"type": "text", "text": part["text"]})
            elif part.get("inline_data"):
                inline = part["inline_data"]
                content.append({"type": "image", "source": {"type": "base64", "media_type": inline.get("mime_type", "image/png"),
                                                            "data": inline.get("data", "")}})
        if json_mode:
            content.append({"type": "text", "text": "Answer with the JSON object only."})
        payload = {"model": self.model, "max_tokens": min(int(max_output_tokens), 16000), "system": system,
                   "messages": [{"role": "user", "content": content or [{"type": "text", "text": "(no input)"}]}]}
        timeout = min(float(getattr(self.cfg, "request_timeout_s", self.TIMEOUT_S) or self.TIMEOUT_S), 300.0)
        req = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
            "x-api-key": self.cfg.api_key, "anthropic-version": API_VERSION, "content-type": "application/json"})
        try:
            with _net.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as exc:
            text = friendly_http_error(exc.code, exc.read().decode("utf-8", "replace"),
                                       (exc.headers.get("retry-after") if exc.headers else "") or "")
            raise BuilderError(f"claude {exc.code}: {text}", text) from exc
        except urllib.error.URLError as exc:
            raise BuilderError(f"cannot reach Claude: {exc.reason}", f"Could not connect to Claude ({exc.reason}).") from exc
        except (TimeoutError, OSError) as exc:
            raise BuilderError("timeout", f"Claude did not answer within {timeout:.0f}s.") from exc
        text = "".join(b.get("text", "") for b in body.get("content") or [] if b.get("type") == "text")
        _count_vision("claude", self.model, (body.get("usage") or {}).get("input_tokens", 0),
                      (body.get("usage") or {}).get("output_tokens", 0))
        if not text.strip():
            raise BuilderError("empty reply", "Claude returned an empty answer.")
        return text
