"""
Friendly Errors
================
Hinglish: Google/OpenAI/Groq ka raw 429 error ek lamba protobuf dump hota hai
(links { description: ... } violations { quota_metric: ... } ...). Ye UI panel
mein dikhana user ke liye bekaar hai. Ye module raw error ko ek chhote, saaf
message mein badalta hai — jaise "Gemini ka quota khatam ho gaya hai ..." —
aur bpy par depend nahi karta, isliye aasani se test hota hai.
"""

import re
from typing import Optional

# Quota / rate-limit pehchanne ke liye signals (lowercase mein match hote hain)
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


def is_quota_error(message: Optional[str]) -> bool:
    """True agar error quota khatam / rate-limit jaisa lagta hai."""
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
    return "AI provider"


def _search(pattern: str, raw: str) -> Optional[str]:
    match = re.search(pattern, raw)
    return match.group(1) if match else None


def quota_message(raw: str) -> str:
    """Raw quota error se ek chhota, actionable message banata hai."""
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
        detail_parts.append(f"limit {limit} requests/din")
    elif limit:
        detail_parts.append(f"limit {limit}")
    detail = f" ({', '.join(detail_parts)})" if detail_parts else ""

    if is_per_minute and not is_daily:
        wait = f" ~{int(float(retry)) + 1} second" if retry else " thodi der"
        return (
            f"{provider} ki requests/minute limit poori ho gayi{detail}. "
            f"{wait.strip().capitalize()} baad dobara try karo."
        )

    return (
        f"{provider} ka quota khatam ho gaya hai{detail}. "
        "Kuch der baad ya kal dobara try karo (daily quota reset hota hai), "
        "ya panel mein koi dusra model/provider chuno."
    )


def friendly_error_message(raw: Optional[str], tool_name: Optional[str] = None) -> str:
    """
    Hinglish: UI mein dikhane layak message. Quota error -> friendly Hinglish message.
    Baaki errors -> "Task failed:" ke saath pehli line, lambai limited (protobuf dump nahi).
    """
    text = (raw or "").strip()
    if not text:
        return "Task could not be completed."

    if is_quota_error(text):
        message = quota_message(text)
        if tool_name == "vision.observe":
            message += " (Sirf visual check skip hua.)"
        return message

    first_line = text.splitlines()[0].strip()
    if len(first_line) > _MAX_PLAIN_LENGTH:
        first_line = first_line[:_MAX_PLAIN_LENGTH].rstrip() + "..."
    return first_line