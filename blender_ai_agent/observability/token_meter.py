"""Token meter: how many AI requests and tokens a run used, for what, and how many were wasted.

Every provider (the agent's Gemini / Claude / OpenAI and the picture-check clients) reports each answer here with the
token counts the API sent back. The controller says which phase is running (plan, build, place, check, fix round N)
and marks waste: a turn whose tool calls were all repeats / failures, a fix round that changed nothing or made it
worse, a request that failed. The run report and the panel show the totals; ~/BlenderAIAgent/usage.json keeps a
per-day count per provider + model (the free quota is counted per day, so 'today' is what matters).
"""

import json
import os
import threading
import time
from typing import Dict, Optional

_LOCK = threading.Lock()


def _new() -> dict:
    return {"requests": 0, "input": 0, "output": 0, "failed": 0, "phases": {}, "wasted": 0, "waste": [],
            "provider": "", "model": "", "started": time.time()}


RUN = _new()
_STATE = {"phase": "build", "last": 0}


def start_run() -> None:
    global RUN
    with _LOCK:
        RUN = _new()
        _STATE.update(phase="build", last=0)


def set_phase(phase: str) -> None:
    _STATE["phase"] = phase or "build"


def record(provider: str, model: str, input_tokens: int, output_tokens: int, phase: Optional[str] = None) -> None:
    input_tokens, output_tokens = int(input_tokens or 0), int(output_tokens or 0)
    phase = phase or _STATE["phase"]
    with _LOCK:
        RUN["requests"] += 1
        RUN["input"] += input_tokens
        RUN["output"] += output_tokens
        RUN["provider"] = provider or RUN["provider"]
        RUN["model"] = model or RUN["model"]
        bucket = RUN["phases"].setdefault(phase, {"requests": 0, "input": 0, "output": 0})
        bucket["requests"] += 1
        bucket["input"] += input_tokens
        bucket["output"] += output_tokens
        _STATE["last"] = input_tokens + output_tokens
    _add_today(provider, model, 1, input_tokens + output_tokens, failed=False)
    try:
        from . import run_trace
        run_trace.note(f"AI     {phase}: {input_tokens:,} in / {output_tokens:,} out tokens ({provider} {model})")
    except Exception:  # noqa: BLE001
        pass


def record_failure(provider: str, model: str, reason: str = "") -> None:
    """A request that came back with an error (quota, overloaded ...). It counts against the daily request limit."""
    with _LOCK:
        RUN["failed"] += 1
    _add_today(provider, model, 1, 0, failed=True, reason=reason)


def mark_waste(reason: str, tokens: Optional[int] = None) -> None:
    """The last request (or `tokens`) bought nothing: repeated / failed tool calls, a fix round with no change."""
    amount = _STATE["last"] if tokens is None else int(tokens)
    if amount <= 0:
        return
    with _LOCK:
        RUN["wasted"] += amount
        RUN["waste"].append(f"{reason} ({amount:,} tokens)")


def phase_tokens(phase: str) -> int:
    bucket = RUN["phases"].get(phase) or {}
    return int(bucket.get("input", 0)) + int(bucket.get("output", 0))


def summary() -> str:
    run = RUN
    if not run["requests"] and not run["failed"]:
        return ""
    total = run["input"] + run["output"]
    phases = ", ".join(f"{name} {b['requests']}" for name, b in run["phases"].items())
    text = (f"AI use: {run['requests']} request(s), {total:,} tokens ({run['input']:,} in / {run['output']:,} out)"
            + (f" - {phases}" if phases else ""))
    if run["failed"]:
        text += f"; {run['failed']} failed request(s)"
    if run["wasted"]:
        share = 100.0 * run["wasted"] / max(1, total)
        text += f". Wasted: {run['wasted']:,} tokens ({share:.0f}%)"
    today = today_text(run["provider"], run["model"])
    if today:
        text += f". {today}"
    return text


def details() -> str:
    """For the run report: every phase and every waste reason."""
    run = RUN
    lines = [summary()]
    for name, bucket in run["phases"].items():
        lines.append(f"  {name:<14} {bucket['requests']:>3} request(s)  {bucket['input']:>9,} in  {bucket['output']:>7,} out")
    for reason in run["waste"][:30]:
        lines.append(f"  wasted: {reason}")
    return "\n".join(line for line in lines if line)


# ------------------------------------------------------------------ per day (the free quota is per day)
def usage_path() -> str:
    folder = os.environ.get("BLENDER_AI_LOG_DIR") or os.path.join(os.path.expanduser("~"), "BlenderAIAgent")
    return os.path.join(os.path.dirname(folder.rstrip("/\\")) if folder.endswith("logs") else folder, "usage.json")


def _day() -> str:
    # Gemini's daily quota resets at midnight Pacific time
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() - 8 * 3600))


def _load() -> dict:
    try:
        with open(usage_path(), encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _add_today(provider: str, model: str, requests: int, tokens: int, failed: bool, reason: str = "") -> None:
    if not provider:
        return
    key = f"{provider} {model}".strip()
    with _LOCK:
        data = _load()
        day = data.setdefault(_day(), {})
        entry = day.setdefault(key, {"requests": 0, "tokens": 0, "failed": 0})
        entry["requests"] += requests
        entry["tokens"] += tokens
        if failed:
            entry["failed"] += 1
            if "quota" in reason.lower() or "429" in reason:
                entry["quota_hit_at"] = time.strftime("%H:%M")
        for old in sorted(data)[:-14]:                     # keep two weeks
            data.pop(old, None)
        try:
            os.makedirs(os.path.dirname(usage_path()), exist_ok=True)
            with open(usage_path(), "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=1)
        except OSError:
            pass


def today(provider: str = "", model: str = "") -> Dict[str, dict]:
    day = _load().get(_day(), {})
    if provider:
        return {k: v for k, v in day.items() if k.startswith(provider) and (not model or k == f"{provider} {model}")}
    return day


def today_text(provider: str = "", model: str = "") -> str:
    entries = today(provider, model)
    if not entries:
        return ""
    requests = sum(e["requests"] for e in entries.values())
    tokens = sum(e["tokens"] for e in entries.values())
    failed = sum(e.get("failed", 0) for e in entries.values())
    hit = next((e["quota_hit_at"] for e in entries.values() if e.get("quota_hit_at")), "")
    text = f"Today ({provider or 'all'} {model}): {requests} request(s), {tokens:,} tokens"
    if failed:
        text += f", {failed} failed"
    if hit:
        text += f", quota ran out at {hit}"
    return text
