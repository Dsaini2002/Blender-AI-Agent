"""ModelProvider (abstract base class)
===================================

    provider.generate(request) -> ModelResponse
"""

import time
from abc import ABC, abstractmethod

# A rate-limit wait longer than this is not waited out: the run would hang for minutes (a Gemini 429 once made
# Blender wait 15+ minutes in one sleep). The error goes up instead, so the Copilot can switch to another AI.
MAX_RETRY_WAIT_S = 20.0


def _stop_event():
    try:
        from ..copilot import activity
        return activity._stop, activity._active
    except Exception:  # noqa: BLE001
        return None, None


def retry_wait(seconds: float, provider: str = "the AI") -> None:
    """Wait before a retry - Stop ends the wait at once; waits longer than MAX_RETRY_WAIT_S are refused."""
    seconds = max(0.0, float(seconds))
    if seconds > MAX_RETRY_WAIT_S:
        raise RuntimeError(f"429 {provider} rate limit / quota: it asks to retry in {seconds:.0f}s - too long to wait")
    stop, active = _stop_event()
    if stop is not None and active is not None and active.is_set():
        if stop.wait(seconds):                       # returns True as soon as Stop is pressed
            raise RuntimeError("Stopped by user while waiting for the AI's rate limit.")
        return
    time.sleep(seconds)


class ModelProvider(ABC):
    """Har concrete provider (OpenAIProvider, AnthropicProvider,"""

    @abstractmethod
    def generate(self, request):
        raise NotImplementedError


def portable_schema(schema: dict, top: bool = False) -> dict:
    """JSON Schema subset every provider accepts (Gemini is the strictest): every node has a type and every object
    has named properties. Free-form objects / 'any' values are sent as a JSON string; input_coercion parses them back."""
    schema = dict(schema or {})
    kind = schema.get("type")
    description = schema.get("description")
    if kind == "object":
        props = schema.get("properties") or {}
        if not props and not top:
            out = {"type": "string", "description": (description + " " if description else "") + "(a JSON object)"}
            return out
        out = {"type": "object", "properties": {k: portable_schema(v) for k, v in props.items()}}
        if schema.get("required"):
            out["required"] = list(schema["required"])
        if description:
            out["description"] = description
        return out
    if kind == "array":
        out = {"type": "array", "items": portable_schema(schema.get("items") or {"type": "number"})}
        if description:
            out["description"] = description
        return out
    if kind in ("string", "number", "integer", "boolean"):
        return schema
    out = {"type": "string", "description": (description + " " if description else "") + "(any value; JSON allowed)"}
    return out


def _meter(provider: str, model: str, response):
    """Count this answer's tokens (run total + today's total) - see observability/token_meter.py."""
    try:
        from ..observability import token_meter
        usage = getattr(response, "usage", None)
        token_meter.record(provider, model, getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0))
    except Exception:  # noqa: BLE001 - counting must never break a request
        pass
    return response


def _count_vision(provider: str, model: str, input_tokens: int, output_tokens: int) -> None:
    try:
        from ..observability import token_meter
        token_meter.record(provider, model, input_tokens, output_tokens)
    except Exception:  # noqa: BLE001
        pass
