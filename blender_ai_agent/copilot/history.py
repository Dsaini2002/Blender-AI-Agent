"""
TaskHistory — Step 6.21
============================
Hinglish: Simple, IN-MEMORY task history — spec explicitly kehta hai
"Phase 6 mein permanent memory system mat banana" (wo Phase 7 hai).
Isliye ye sirf session ke andar recent tasks track karta hai.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class TaskHistoryEntry:
    task_id: str
    description: str
    success: bool
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def icon(self) -> str:
        return "✓" if self.success else "✗"


class TaskHistory:

    def __init__(self):
        self._entries: List[TaskHistoryEntry] = []

    def add(self, task_id: str, description: str, success: bool) -> None:
        self._entries.append(TaskHistoryEntry(task_id=task_id, description=description, success=success))

    def list_recent(self, limit: int = 10) -> List[TaskHistoryEntry]:
        """Hinglish: Sabse naye task pehle (reverse-chronological)."""
        return list(reversed(self._entries))[:limit]

    def find_by_task_id(self, task_id: str) -> Optional[TaskHistoryEntry]:
        for entry in self._entries:
            if entry.task_id == task_id:
                return entry
        return None

    def __len__(self) -> int:
        return len(self._entries)