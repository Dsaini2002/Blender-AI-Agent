"""Logger"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional


@dataclass
class LogEvent:
    event: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class Logger:

    def __init__(self):
        self._events: List[LogEvent] = []
        self.callback: Optional[Callable[[str, Dict[str, Any]], None]] = None

    def info(self, event: str, **data) -> None:
        self._record(event, data)

    def error(self, event: str, **data) -> None:
        self._record(f"error.{event}", data)

    def _record(self, event: str, data: Dict[str, Any]) -> None:
        self._events.append(LogEvent(event=event, data=data))
        try:
            from . import run_trace
            run_trace.on_event(event, data)            # live_trace.txt: written while the run goes
        except Exception:  # noqa: BLE001 — tracing must never break a run
            pass
        callback = self.callback
        if callback is not None:
            try:
                callback(event, dict(data))
            except Exception:  # noqa: BLE001 
                pass

    def get_events(self) -> List[LogEvent]:
        return list(self._events)

    def events_for(self, task_id: str) -> List[LogEvent]:
        return [e for e in self._events if e.data.get("task_id") == task_id]
