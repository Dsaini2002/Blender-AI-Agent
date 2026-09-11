"""
EventBus — Step 6.23 / 6.24
================================
Hinglish: Agent ke internal events (TASK_STARTED, TOOL_COMPLETED, etc.)
ko UI tak pahunchane ka decoupled mechanism — publish/subscribe pattern.

Agent ko UI ka pata nahi hona chahiye, aur UI ko Agent ke internal
code mein nahi ghusna chahiye. EventBus beech mein ek loose-coupling
layer hai.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List


class CopilotEvent:
    TASK_STARTED = "TASK_STARTED"
    PLAN_CREATED = "PLAN_CREATED"
    TOOL_STARTED = "TOOL_STARTED"
    TOOL_COMPLETED = "TOOL_COMPLETED"
    TOOL_FAILED = "TOOL_FAILED"
    VALIDATION_STARTED = "VALIDATION_STARTED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    REPAIR_STARTED = "REPAIR_STARTED"
    TASK_COMPLETED = "TASK_COMPLETED"
    TASK_FAILED = "TASK_FAILED"


@dataclass
class EventPayload:
    name: str
    data: Dict[str, Any] = field(default_factory=dict)


class EventBus:

    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_name: str, callback: Callable) -> None:
        self._subscribers.setdefault(event_name, []).append(callback)

    def publish(self, event_name: str, **data) -> None:
        payload = EventPayload(name=event_name, data=data)
        for callback in self._subscribers.get(event_name, []):
            callback(payload)

    def unsubscribe(self, event_name: str, callback: Callable) -> None:
        if event_name in self._subscribers and callback in self._subscribers[event_name]:
            self._subscribers[event_name].remove(callback)