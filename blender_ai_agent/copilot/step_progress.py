"""
Progress tracking — "kitna ho gaya, kitna time aur lagega"
=============================================================
NOTE: Ye "step-wise progress + ETA" wala module hai (ProgressTracker, ProgressHistory, get_tracker).
Purana copilot/progress.py (ProgressState, StepStatus) alag hai aur waisa hi rehta hai — naam isiliye alag rakha.
Hinglish: Ye module pure Python hai (bpy nahi) aur thread-safe hai: worker thread tracker ko update karta hai,
Blender ka UI (ui/progress_panel.py) usse padhta hai.

Do tarah ke progress:
  1. Step-wise (bade task ko todkar): total steps pata hain -> percent + ETA (bacha hua time)
  2. Single task: total pata nahi -> elapsed time + "aam taur par ~X lagta hai" (pichhle runs se seekha hua)

ETA kaise nikalta hai: har step ka expected time = pichhle runs ke asli timings ka median
("skill" steps tez, "agent" = LLM wale steps dheere). Is run mein jaise-jaise steps khatam hote hain,
speed ka factor seekh kar bacha hua ETA sudharta rehta hai.
"""

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

DEFAULT_SECONDS: Dict[str, float] = {"agent": 20.0, "skill": 3.0}
HISTORY_LIMIT = 20


# --------------------------------------------------------------------------- formatting
def format_duration(seconds: Optional[float]) -> str:
    """35 -> '0:35', 125 -> '2:05', 3700 -> '1:01:40', None -> '--:--'."""
    if seconds is None:
        return "--:--"
    total = int(round(max(0.0, seconds)))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def ascii_bar(percent: float, width: int = 10) -> str:
    """40 -> '####------' (sirf ASCII, har Blender font par sahi dikhta hai)."""
    filled = int(round(width * max(0.0, min(100.0, percent)) / 100.0))
    return "#" * filled + "-" * (width - filled)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# --------------------------------------------------------------------------- history
def default_history_path() -> str:
    return os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "progress_history.json")


class ProgressHistory:
    """Pichhle steps ke asli timings (seconds) — estimates behtar karne ke liye. path=None => sirf memory."""

    def __init__(self, path: Optional[str] = None):
        self._path = path
        self._data: Dict[str, List[float]] = {kind: [] for kind in DEFAULT_SECONDS}
        self._load()

    def _load(self) -> None:
        if not self._path:
            return
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            for kind in DEFAULT_SECONDS:
                values = loaded.get(kind, [])
                self._data[kind] = [float(v) for v in values if isinstance(v, (int, float)) and 0 < v < 3600][-HISTORY_LIMIT:]
        except (OSError, ValueError, AttributeError, TypeError):
            pass                                   # kharab/missing file -> default estimates

    def _save(self) -> None:
        if not self._path:
            return
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as handle:
                json.dump(self._data, handle)
        except (OSError, ValueError):
            pass                                   # estimates ka save na hona kabhi task ko na roke

    def record(self, kind: str, seconds: float) -> None:
        if kind not in self._data or not (0.05 < seconds < 3600):
            return
        self._data[kind] = (self._data[kind] + [float(seconds)])[-HISTORY_LIMIT:]
        self._save()

    def estimate(self, kind: str) -> float:
        values = sorted(self._data.get(kind, []))
        if not values:
            return DEFAULT_SECONDS.get(kind, DEFAULT_SECONDS["agent"])
        middle = len(values) // 2
        return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2


# --------------------------------------------------------------------------- tracker
@dataclass
class Step:
    label: str
    kind: str = "agent"                            # "agent" (LLM) | "skill" (tez, bina LLM)
    status: str = "pending"                        # pending | running | done | failed | skipped
    expected: float = 0.0
    started: Optional[float] = None
    ended: Optional[float] = None
    note: str = ""


@dataclass
class Progress:
    """UI/status line ke liye ek jhalak (snapshot)."""
    state: str = "idle"                            # idle | running | done
    request: str = ""
    total: int = 0                                 # 0 => step-wise nahi (single task)
    index: int = 0                                 # current step (1-based)
    completed: int = 0
    failed: int = 0
    percent: Optional[float] = None
    elapsed: float = 0.0
    eta: Optional[float] = None
    typical: Optional[float] = None                # single task: aam taur par kitna lagta hai
    label: str = ""
    ok: Optional[bool] = None
    tool_events: int = 0
    turns: int = 0
    steps: List[Dict[str, object]] = field(default_factory=list)


class ProgressTracker:

    def __init__(self, history: Optional[ProgressHistory] = None, clock: Callable[[], float] = time.monotonic):
        self._lock = threading.RLock()
        self._clock = clock
        self._history = history if history is not None else ProgressHistory(None)
        self._reset_locked()

    # ---- lifecycle
    def _reset_locked(self) -> None:
        self._state = "idle"
        self._request = ""
        self._steps: List[Step] = []
        self._started: Optional[float] = None
        self._ended: Optional[float] = None
        self._current: Optional[int] = None
        self._tool_events = 0
        self._turns = 0
        self._ok: Optional[bool] = None

    def reset(self) -> None:
        with self._lock:
            self._reset_locked()

    def begin(self, request: str, steps: Optional[List[str]] = None, kinds: Optional[List[str]] = None) -> None:
        """Naya task shuru. `steps` diye to step-wise (percent+ETA), warna single (elapsed)."""
        with self._lock:
            self._reset_locked()
            self._state = "running"
            self._request = request
            self._started = self._clock()
            for position, label in enumerate(steps or []):
                kind = kinds[position] if kinds and position < len(kinds) else "agent"
                self._steps.append(Step(label=label, kind=kind, expected=self._history.estimate(kind)))

    def start_step(self, index: int, kind: Optional[str] = None) -> None:
        with self._lock:
            step = self._steps[index]
            if kind:
                step.kind = kind
                step.expected = self._history.estimate(kind)
            step.status = "running"
            step.started = self._clock()
            self._current = index

    def finish_step(self, index: int, ok: bool, note: str = "") -> None:
        with self._lock:
            step = self._steps[index]
            step.status = "done" if ok else "failed"
            step.ended = self._clock()
            step.note = note
            if step.started is not None:
                self._history.record(step.kind, step.ended - step.started)
            if self._current == index:
                self._current = None

    def skip_remaining(self, note: str = "") -> None:
        with self._lock:
            for step in self._steps:
                if step.status in ("pending", "running"):
                    step.status = "skipped"
                    step.note = note
            self._current = None

    def note_event(self, event: str) -> None:
        """Agent ke logger events — activity ginte hain (single task ke progress ke liye)."""
        with self._lock:
            if isinstance(event, str):
                if event.startswith("tool."):
                    self._tool_events += 1
                elif event == "model.request":
                    self._turns += 1

    def finish(self, ok: Optional[bool] = None) -> None:
        with self._lock:
            self._state = "done"
            self._ended = self._clock()
            self._ok = ok
            if self._steps and ok is None:
                self._ok = all(s.status == "done" for s in self._steps)

    # ---- reading
    def is_running(self) -> bool:
        with self._lock:
            return self._state == "running"

    def _speed_factor_locked(self, now: float) -> float:
        """Is run mein steps expected se kitne tez/dheere chal rahe hain (0.25x - 4x)."""
        actual = expected = 0.0
        for step in self._steps:
            if step.status in ("done", "failed") and step.started is not None and step.ended is not None:
                actual += step.ended - step.started
                expected += step.expected
        return _clamp(actual / expected, 0.25, 4.0) if expected > 0 and actual > 0 else 1.0

    def snapshot(self) -> Progress:
        with self._lock:
            now = self._clock()
            end = self._ended if self._state == "done" and self._ended is not None else now
            elapsed = (end - self._started) if self._started is not None else 0.0
            snap = Progress(state=self._state, request=self._request, elapsed=elapsed, ok=self._ok,
                            tool_events=self._tool_events, turns=self._turns)
            if self._state == "idle":
                return snap

            if not self._steps:                                   # single task
                snap.typical = self._history.estimate("agent")
                snap.label = self._request
                if self._state == "done":
                    snap.percent = 100.0
                return snap

            total = len(self._steps)
            snap.total = total
            snap.completed = sum(1 for s in self._steps if s.status == "done")
            snap.failed = sum(1 for s in self._steps if s.status == "failed")
            finished = sum(1 for s in self._steps if s.status in ("done", "failed", "skipped"))
            current_index = self._current if self._current is not None else min(finished, total - 1)
            snap.index = min(total, current_index + 1) if self._state == "running" else total
            snap.label = self._steps[min(current_index, total - 1)].label
            snap.steps = [{"label": s.label, "status": s.status, "kind": s.kind, "note": s.note,
                           "seconds": (s.ended - s.started) if s.started is not None and s.ended is not None else None}
                          for s in self._steps]

            if self._state == "done":
                snap.percent = 100.0
                snap.eta = 0.0
                return snap

            if finished == total:                                  # saare steps ho chuke, bas summary baaki
                snap.percent, snap.eta = 100.0, 0.0
                return snap

            speed = self._speed_factor_locked(now)
            weights = [max(0.1, s.expected * speed) for s in self._steps]
            done_weight = sum(w for s, w in zip(self._steps, weights) if s.status in ("done", "failed", "skipped"))
            current_fraction = 0.0
            remaining = sum(w for s, w in zip(self._steps, weights) if s.status == "pending")
            for s, w in zip(self._steps, weights):
                if s.status == "running" and s.started is not None:
                    spent = now - s.started
                    current_fraction = min(0.95, spent / w)
                    remaining += max(w * 0.1, w - spent)       # step expected se zyada khinch jaye to bhi thoda bacha dikhao
            total_weight = sum(weights)
            snap.percent = _clamp(100.0 * (done_weight + current_fraction * next(
                (w for s, w in zip(self._steps, weights) if s.status == "running"), 0.0)) / total_weight, 0.0, 99.0)
            snap.eta = remaining
            return snap

    def status_line(self, event: Optional[str] = None) -> str:
        """Chhoti, ek line ki status (panel ka label chhota hai): '2/5 [####------] 40%  ~0:52 left'."""
        snap = self.snapshot()
        if snap.state == "idle":
            return ""
        if snap.state == "done":
            if snap.total:
                failed = f" ({snap.failed} failed)" if snap.failed else ""
                return f"Done {snap.completed}/{snap.total}{failed} in {format_duration(snap.elapsed)}"
            return f"Done in {format_duration(snap.elapsed)}"
        if snap.total:
            return f"{snap.index}/{snap.total} [{ascii_bar(snap.percent or 0)}] {snap.percent or 0:.0f}%  ~{format_duration(snap.eta)} left"
        return f"Working {format_duration(snap.elapsed)}  (usually ~{format_duration(snap.typical)})"


# --------------------------------------------------------------------------- shared instance (UI isse padhta hai)
_tracker: Optional[ProgressTracker] = None
_tracker_lock = threading.Lock()


def get_tracker() -> ProgressTracker:
    global _tracker
    with _tracker_lock:
        if _tracker is None:
            _tracker = ProgressTracker(history=ProgressHistory(default_history_path()))
        return _tracker