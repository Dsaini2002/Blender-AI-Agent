"""
Logger — Step 4.9
====================
Hinglish: Simple, structured event logger. Har event ek dict hai
(timestamp + event name + data) — taaki debugging ke waqt exactly
pata chale "kya hua tha".
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass
class LogEvent:
    event: str
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class Logger:
    """Hinglish: In-memory logger — events list mein store hote hain, query kiye ja sakte hain."""

    def __init__(self):
        self._events: List[LogEvent] = []

    def info(self, event: str, **data) -> None:
        self._events.append(LogEvent(event=event, data=data))

    def error(self, event: str, **data) -> None:
        self._events.append(LogEvent(event=f"error.{event}", data=data))

    def get_events(self) -> List[LogEvent]:
        return list(self._events)

    def events_for(self, task_id: str) -> List[LogEvent]:
        return [e for e in self._events if e.data.get("task_id") == task_id]