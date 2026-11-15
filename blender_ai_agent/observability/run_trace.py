"""What happened in a run, written so a person can find the error.

Two files in ~/BlenderAIAgent/logs (or BLENDER_AI_LOG_DIR):

  live_trace.txt        written WHILE the run goes: every step, model call and tool call is appended and flushed at
                        once. If Blender hangs or crashes, the last lines say what was running. When nothing happens
                        for WATCHDOG_S seconds, the Python stack of every thread is dumped into it (where it is stuck).
  <time>_report.txt     written when the run ends: the request, versions, team plan, every step and tool with its
                        time, ALL errors in one place (tool, arguments, message), the automatic check rounds and
                        where the time went. Send this file (with the .json log) when something goes wrong.

API keys are never written: only whether a key is set.
"""

import faulthandler
import json
import os
import platform
import sys
import threading
import time
import traceback
from typing import Any, Dict, List, Optional

WATCHDOG_S = 90
LIVE_NAME = "live_trace.txt"
CRASH_NAME = "crash_trace.txt"
KEY_NAMES = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")

_lock = threading.RLock()
_state: Dict[str, Any] = {"file": None, "started": 0.0, "last": 0.0, "pending": None, "steps": []}
_crash_file = None


def log_folder() -> str:
    folder = os.environ.get("BLENDER_AI_LOG_DIR") or os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "logs")
    os.makedirs(folder, exist_ok=True)
    return folder


def live_path() -> str:
    return os.path.join(log_folder(), LIVE_NAME)


def environment() -> Dict[str, Any]:
    info = {"python": sys.version.split()[0], "os": f"{platform.system()} {platform.release()}",
            "keys_set": [k for k in KEY_NAMES if os.environ.get(k, "").strip()]}
    try:
        import bpy
        info["blender"] = getattr(bpy.app, "version_string", "?")
        info["render_engine"] = bpy.context.scene.render.engine
        info["scene_objects"] = len(bpy.context.scene.objects)
    except Exception:  # noqa: BLE001 — also used without Blender (tests)
        pass
    try:
        from .. import bl_info
        info["addon_version"] = ".".join(str(v) for v in bl_info.get("version", ()))
    except Exception:  # noqa: BLE001
        pass
    return info


def _short(value: Any, limit: int = 300) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# ---------------------------------------------------------------- live trace
def _write(line: str) -> None:
    handle = _state.get("file")
    if handle is None:
        return
    try:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())             # on disk even if Blender dies the next moment
    except Exception:  # noqa: BLE001 — tracing must never break a run
        pass


def _arm_watchdog() -> None:
    handle = _state.get("file")
    if handle is None:
        return
    try:
        faulthandler.cancel_dump_traceback_later()
        faulthandler.dump_traceback_later(WATCHDOG_S, repeat=True, file=handle)
    except Exception:  # noqa: BLE001 — e.g. no real file descriptor
        pass


def _stamp() -> str:
    now = time.time()
    return f"{time.strftime('%H:%M:%S')} +{now - _state['started']:6.1f}s"


def begin(request: str, provider: str = "", model: str = "") -> None:
    """A new run: start a fresh live_trace.txt."""
    with _lock:
        end_file()
        try:
            handle = open(live_path(), "w", encoding="utf-8")
        except OSError:
            return
        _state.update(file=handle, started=time.time(), last=time.time(), pending=None, steps=[])
        env = environment()
        _write("BLENDER AI AGENT - LIVE TRACE (written while the run goes; the last lines show what was running)")
        _write(f"started  {time.strftime('%Y-%m-%d %H:%M:%S')}")
        _write(f"provider {provider or '?'}   model {model or '?'}")
        _write("env      " + _short(env, 400))
        _write("request  " + _short(request, 600))
        _write(f"(if nothing is written for {WATCHDOG_S}s, the Python stack of every thread is dumped below: that is "
               "where it is stuck)")
        _write("-" * 100)
        _arm_watchdog()


def note(text: str) -> None:
    """A line from the controller / the automatic check (progress, renders, vision scores ...)."""
    with _lock:
        if _state.get("file") is None:
            return
        _write(f"{_stamp()}  {text}")
        _state["last"] = time.time()
        _arm_watchdog()


_WAITING = {"model.request": "waiting for the AI model's reply", "tool.execute": "running the tool"}


def on_event(event: str, data: Dict[str, Any]) -> None:
    """Every logger event of the agent (model.request, tool.execute, validation.success, error.* ...)."""
    with _lock:
        if _state.get("file") is None:
            return
        now = time.time()
        pending = _state.get("pending")
        took = f" ({now - pending[1]:.1f}s)" if pending else ""
        if event == "model.request":
            line = f"MODEL  turn {data.get('turn')} -> {_WAITING[event]} …"
        elif event == "model.plan":
            line = f"MODEL  answered{took}: wants {_short(data.get('planned_tools'), 400)}"
        elif event == "tool.execute":
            line = f"TOOL   {data.get('tool')} {_short(data.get('arguments'), 350)}"
        elif event == "validation.success":
            line = f"  ok{took}  {data.get('tool')} -> {_short(data.get('result'), 250)}"
        elif event.startswith("error."):
            line = (f"  ERROR{took} [{event[6:]}] {data.get('tool', '')} {data.get('code', '')}: "
                    f"{_short(data.get('message') or data.get('error') or data, 500)}")
        elif event == "task.start":
            line = f"STEP   start: {_short(data.get('message'), 200)}"
        elif event == "task.complete":
            line = f"STEP   done{took}"
        elif event == "check.progress":
            line = f"CHECK  {data.get('text', '')}"
        elif event == "check.review":
            parts = [f"REVIEW round {data.get('round')}: " + (f"vision {data.get('score'):g}/10" if data.get("score")
                     is not None else f"vision not done ({data.get('vision_note', '')})")]
            if data.get("missing"):
                parts.append("        missing: " + ", ".join(data["missing"]))
            for p in (data.get("problems") or []) + (data.get("geometry") or []):
                parts.append("        " + _short(p, 300))
            parts.append(f"        -> {'fix needed' if data.get('needs_fix') else 'no fix needed'}; files: {data.get('folder', '')}")
            line = "\n".join(parts)
        elif event == "check.fix_sent":
            line = f"FIX    round {data.get('round')}: the problems above were sent to the agent ({data.get('file', '')})"
        elif event.startswith("team."):
            line = f"TEAM   {event[5:]}: {_short({k: v for k, v in data.items() if k != 'raw'}, 600)}"
        else:
            line = f"       {event} {_short({k: v for k, v in data.items() if k != 'task_id'}, 300)}"
        _write(f"{_stamp()}  {line}")
        _state["pending"] = (event, now) if event in _WAITING else None
        _state["last"] = now
        _arm_watchdog()


def exception(where: str, exc: BaseException) -> None:
    with _lock:
        if _state.get("file") is None:
            return
        _write(f"{_stamp()}  EXCEPTION in {where}: {type(exc).__name__}: {exc}")
        for line in traceback.format_exception(type(exc), exc, exc.__traceback__):
            for part in line.rstrip().splitlines():
                _write("    " + part)


def end_file(result_text: str = "") -> None:
    with _lock:
        handle = _state.get("file")
        if handle is None:
            return
        if result_text:
            _write("-" * 100)
            _write(f"{_stamp()}  FINISHED: {_short(result_text, 600)}")
        try:
            faulthandler.cancel_dump_traceback_later()
        except Exception:  # noqa: BLE001
            pass
        try:
            handle.close()
        except Exception:  # noqa: BLE001
            pass
        _state["file"] = None


def enable_crash_dump() -> None:
    """A hard crash of Blender (not a Python error) still leaves the Python stacks in crash_trace.txt."""
    global _crash_file
    if _crash_file is not None:
        return
    try:
        _crash_file = open(os.path.join(log_folder(), CRASH_NAME), "w", encoding="utf-8")
        _crash_file.write(f"Blender AI Agent crash trace - session started {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                          "Empty below = no crash in this session.\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:  # noqa: BLE001
        _crash_file = None


def disable_crash_dump() -> None:
    global _crash_file
    try:
        if _crash_file is not None:
            faulthandler.disable()
            _crash_file.close()
    except Exception:  # noqa: BLE001
        pass
    _crash_file = None


# ---------------------------------------------------------------- report
def build_report(payload: Dict[str, Any], env: Optional[Dict[str, Any]] = None) -> str:
    """A readable report of one run from the .json run log."""
    events: List[Dict[str, Any]] = payload.get("events") or []
    lines = ["BLENDER AI AGENT - RUN REPORT", "=" * 100]
    ok = payload.get("success")
    lines.append(f"Result     {'OK' if ok else 'FAILED' if ok is False else 'unknown'} in {payload.get('seconds')} s")
    lines.append(f"Provider   {payload.get('provider')}   model {payload.get('model')}")
    for key, value in (env or {}).items():
        lines.append(f"{key:<10} {value}")
    lines += ["", "REQUEST", "-" * 100, (payload.get("request") or "").strip(), ""]
    if payload.get("ai_use"):
        lines += ["AI USE (requests and tokens - and what was wasted)", "-" * 100, str(payload["ai_use"]), ""]

    # timings
    def parse(t):
        try:
            from datetime import datetime
            return datetime.fromisoformat(t).timestamp()
        except Exception:  # noqa: BLE001
            return None

    model_s = tool_s = 0.0
    tool_times: Dict[str, List[float]] = {}
    errors, steps, team, checks = [], [], [], []
    last_args: Dict[str, str] = {}
    for i, e in enumerate(events):
        nxt = events[i + 1] if i + 1 < len(events) else None
        span = None
        if nxt is not None:
            a, b = parse(e.get("t", "")), parse(nxt.get("t", ""))
            span = (b - a) if a is not None and b is not None else None
        name = e.get("event", "")
        if name == "model.request" and span is not None:
            model_s += span
        if name == "tool.execute":
            last_args[e.get("tool", "")] = e.get("arguments", "")
            if span is not None:
                tool_s += span
                tool_times.setdefault(e.get("tool", "?"), []).append(span)
        if name.startswith("error."):
            errors.append(e)
        if name == "task.start":
            steps.append(e)
        if name.startswith("team."):
            team.append(e)
        if name.startswith("check.") or name.startswith("verify."):
            checks.append(e)

    lines += ["WHERE THE TIME WENT", "-" * 100,
              f"waiting for the AI model  {model_s:7.1f} s",
              f"running tools             {tool_s:7.1f} s",
              f"other (checks, renders)   {max(0.0, float(payload.get('seconds') or 0) - model_s - tool_s):7.1f} s"]
    slow = sorted(((sum(v), k, len(v)) for k, v in tool_times.items()), reverse=True)[:6]
    if slow:
        lines.append("slowest tools: " + ", ".join(f"{k} {s:.1f}s x{n}" for s, k, n in slow))
    lines.append("")

    lines += [f"ERRORS ({len(errors)})", "-" * 100]
    if not errors:
        lines.append("none")
    for e in errors:
        tool = e.get("tool", "")
        lines.append(f"{e.get('t', '')[11:19]}  {e.get('event')}  {tool}  {e.get('code', '')}")
        message = e.get("message") or e.get("error") or ""
        if message:
            lines.append(f"    message:   {message}")
        args = e.get("arguments") or last_args.get(tool)
        if args:
            lines.append(f"    arguments: {args}")
    lines.append("")

    if team:
        lines += ["TEAM PLAN", "-" * 100]
        for e in team:
            detail = {k: v for k, v in e.items() if k not in ("t", "event", "raw")}
            lines.append(f"{e.get('event')}: {_short(detail, 900)}")
        lines.append("")

    reviews = [e for e in events if e.get("event") == "check.review"]
    if reviews:
        lines += [f"AUTOMATIC CHECK ROUNDS ({len(reviews)})", "-" * 100,
                  "Each round: what the check found -> it is sent to the agent -> the agent fixes -> checked again.", ""]
        for e in reviews:
            score = e.get("score")
            lines.append(f"Round {e.get('round')}  {e.get('t', '')[11:19]}  " +
                         (f"vision {score:g}/10" if score is not None else f"vision not done: {e.get('vision_note', '')}"))
            if e.get("folder"):
                lines.append(f"    images + review.txt + fix_prompt.txt: {e.get('folder')}")
            if e.get("missing"):
                lines.append("    missing: " + ", ".join(e["missing"]))
            for p in e.get("problems") or []:
                lines.append(f"    vision:   {p}")
            for p in e.get("geometry") or []:
                lines.append(f"    geometry: {p}")
            if e.get("console"):
                lines.append(f"    console errors: {e.get('console')}")
            lines.append("    -> " + ("fix needed: sent to the agent as the next round" if e.get("needs_fix") else "no fix needed"))
            lines.append("")

    lines += [f"STEPS ({len(steps)})", "-" * 100]
    for e in steps:
        lines.append(f"{e.get('t', '')[11:19]}  {_short(e.get('message', ''), 160)}")
    lines.append("")

    lines += ["TIMELINE", "-" * 100]
    for e in events:
        name = e.get("event", "")
        t = e.get("t", "")[11:19]
        if name == "tool.execute":
            lines.append(f"{t}  TOOL  {e.get('tool')} {_short(e.get('arguments', ''), 220)}")
        elif name == "validation.success":
            lines.append(f"{t}    ok  {_short(e.get('result', ''), 160)}")
        elif name.startswith("error."):
            lines.append(f"{t}    ERROR {e.get('tool', '')}: {_short(e.get('message', '') or e.get('error', ''), 200)}")
        elif name == "model.plan":
            lines.append(f"{t}  MODEL wants {_short(e.get('planned_tools', ''), 200)}")
        elif name == "task.start":
            lines.append(f"{t}  STEP  {_short(e.get('message', ''), 160)}")
        elif name == "check.progress":
            lines.append(f"{t}  CHECK {e.get('text', '')}")
        elif name == "check.review":
            lines.append(f"{t}  REVIEW round {e.get('round')}: score {e.get('score')}, {len(e.get('missing') or [])} missing, "
                         f"{len(e.get('problems') or [])} vision + {len(e.get('geometry') or [])} geometry problem(s)")
        elif name == "check.fix_sent":
            lines.append(f"{t}  FIX   round {e.get('round')} sent to the agent ({e.get('file', '')})")
        elif name not in ("model.request", "task.complete"):
            lines.append(f"{t}  {name} {_short({k: v for k, v in e.items() if k not in ('t', 'event', 'task_id')}, 200)}")
    lines += ["", "REPLY / AUTOMATIC CHECK", "-" * 100, (payload.get("reply") or "").strip(), ""]
    lines.append("Send this file together with the .json run log of the same time when something went wrong.")
    return "\n".join(lines) + "\n"


def write_report(json_path: str, payload: Dict[str, Any]) -> str:
    path = json_path[:-5] + "_report.txt" if json_path.endswith(".json") else json_path + "_report.txt"
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(build_report(payload, environment()))
        return path
    except OSError:
        return ""
