"""Friendly Errors"""

import re
from typing import Optional

_QUOTA_SIGNALS = (
    "429",
    "quota",
    "rate limit",
    "rate_limit",
    "ratelimit",
    "resource_exhausted",
    "resource exhausted",
    "too many requests",
    "exceeded your current",
)

_MAX_PLAIN_LENGTH = 220


_AUTH_SIGNALS = ("401", "invalid api key", "invalid_api_key", "api key not valid", "unauthorized",
                 "incorrect api key", "authentication_error", "permission_denied", "api_key_invalid")


def is_auth_error(message: Optional[str]) -> bool:
    """The API key is wrong, expired or revoked (not a quota problem)."""
    lowered = (message or "").lower()
    return any(signal in lowered for signal in _AUTH_SIGNALS)


def is_quota_error(message: Optional[str]) -> bool:
    lowered = (message or "").lower()
    return any(signal in lowered for signal in _QUOTA_SIGNALS)


def _provider_name(raw: str) -> str:
    lowered = raw.lower()
    if "generativelanguage" in lowered or "gemini" in lowered or "ai.google.dev" in lowered:
        return "Gemini"
    if "groq" in lowered:
        return "Groq"
    if "openai" in lowered:
        return "OpenAI"
    if "claude" in lowered or "anthropic" in lowered:
        return "Claude"
    return "AI provider"


def _search(pattern: str, raw: str) -> Optional[str]:
    match = re.search(pattern, raw)
    return match.group(1) if match else None


def too_large_for_plan(raw: Optional[str]):
    """(limit, requested) when ONE request is bigger than the plan's tokens-per-minute (Groq's free plan: 8,000) -
    waiting does not help, the request never fits. None otherwise."""
    text = raw or ""
    if "tokens per minute" not in text.lower() and "tpm" not in text.lower():
        return None
    limit = _search(r"Limit\s*(\d+)", text)
    requested = _search(r"Requested\s*(\d+)", text)
    if limit and requested and int(requested) > int(limit):
        return int(limit), int(requested)
    if "request too large" in text.lower() and limit:
        return int(limit), int(requested or 0)
    return None


def too_large_message(raw: str) -> str:
    limit, requested = too_large_for_plan(raw) or (0, 0)
    provider = _provider_name(raw)
    need = f" - one step of the agent needs about {requested:,} (its instructions + tools)" if requested else ""
    return (f"{provider}'s plan allows only {limit:,} tokens per minute{need}, so {provider} can not run the agent. "
            f"Waiting does not help. Use Gemini or Claude, or add a payment method in the {provider} console "
            f"(Developer plan: much higher limit, pay per use).")


def _wait_text(seconds: float) -> str:
    if seconds >= 3600:
        return f"in ~{seconds / 3600:.0f} h"
    if seconds >= 120:
        return f"in ~{seconds / 60:.0f} min"
    return f"in ~{int(seconds) + 1} seconds"


def quota_message(raw: str) -> str:
    provider = _provider_name(raw)
    model = _search(r'model:\s*"?([\w.\-/]+)"?', raw) or _search(r'value:\s*"(gemini[\w.\-]*)"', raw)
    limit = _search(r"limit:\s*(\d+)", raw)
    retry = _search(r"retry in ([\d.]+)\s*s", raw)

    is_daily = "perday" in raw.lower().replace("_", "").replace(" ", "") or "per day" in raw.lower()
    is_per_minute = "perminute" in raw.lower().replace("_", "").replace(" ", "")

    detail_parts = []
    if model:
        detail_parts.append(model)
    if limit and is_daily:
        detail_parts.append(f"limit {limit} requests/day")
    elif limit:
        detail_parts.append(f"limit {limit}")
    detail = f" ({', '.join(detail_parts)})" if detail_parts else ""

    if retry and float(retry) >= 3600:
        return (f"{provider} quota is used up{detail} - it is free again {_wait_text(float(retry))}. "
                "Pick another provider in the panel to go on now.")
    if is_per_minute and not is_daily:
        wait = _wait_text(float(retry)) if retry else "in a little while"
        return (
            f"{provider} requests/minute limit reached{detail}. "
            f"Try again {wait.strip()}."
        )

    return (
        f"{provider} quota is used up{detail}. "
        "Try again later or tomorrow (the daily quota resets), "
        "or pick another model / provider in the panel."
    )


def friendly_error_message(raw: Optional[str], tool_name: Optional[str] = None) -> str:
    text = (raw or "").strip()
    if not text:
        return "Task could not be completed."

    if too_large_for_plan(text):
        return too_large_message(text)
    if is_quota_error(text):
        message = quota_message(text)
        if tool_name == "vision.observe":
            message += " (Only the visual check was skipped.)"
        return message
    if is_auth_error(text):
        return (f"The {_provider_name(text)} API key is not valid any more (wrong, expired or deleted). Click the gear "
                "in the AI Copilot panel, press Change, paste a new key and press Submit Key.")

    first_line = text.splitlines()[0].strip()
    if len(first_line) > _MAX_PLAIN_LENGTH:
        first_line = first_line[:_MAX_PLAIN_LENGTH].rstrip() + "..."
    return first_line

def providers_failed_message(failures) -> str:
    """Every AI that was tried, in order, each with its own reason (the one picked in the panel first)."""
    parts = []
    for index, (name, raw) in enumerate(failures):
        label = {"gemini": "Gemini", "groq": "Groq", "claude": "Claude", "openai": "OpenAI"}.get(name, name or "AI")
        reason = friendly_error_message(raw)
        prefix = f"{label} failed: " if index == 0 else f"Then tried {label} instead: "
        parts.append(prefix + reason)
    return " | ".join(parts) if parts else "Task could not be completed."
