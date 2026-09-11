"""
MemoryManager — Step 7.5
============================
Hinglish: Agent isi class se baat karega — store ke internal
implementation (in-memory, SQLite, etc.) ka pata nahi chalega.

    Agent -> MemoryManager -> MemoryStore
"""

from typing import List, Optional

from .models import Memory
from .store import MemoryStore


class MemoryManager:

    def __init__(self, store: MemoryStore):
        # Dependency Injection — store bahar se di gayi hai
        self._store = store

    def remember(self, memory: Memory) -> None:
        self._store.save(memory)

    def recall(self, query: str) -> List[Memory]:
        return self._store.search(query)

    def forget(self, memory_id: str) -> bool:
        return self._store.delete(memory_id)

    def get(self, memory_id: str) -> Optional[Memory]:
        return self._store.get(memory_id)