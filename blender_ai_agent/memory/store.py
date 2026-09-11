"""
MemoryStore — Step 7.4
==========================
Hinglish: Agent ko storage technology (in-memory, JSON file, SQLite,
vector DB) ke saath tightly couple nahi karna — Dependency Inversion.
Abhi sirf InMemoryStore banate hain; future mein JSONMemoryStore,
SQLiteMemoryStore isi contract ko implement karenge.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from .models import Memory


class MemoryStore(ABC):

    @abstractmethod
    def save(self, memory: Memory) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, memory_id: str) -> Optional[Memory]:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str) -> List[Memory]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        raise NotImplementedError


class InMemoryStore(MemoryStore):
    """Hinglish: Session ke andar hi rehta hai — restart pe khatam. Phase 7 ka starting point."""

    def __init__(self):
        self._memories: Dict[str, Memory] = {}

    def save(self, memory: Memory) -> None:
        self._memories[memory.id] = memory

    def get(self, memory_id: str) -> Optional[Memory]:
        return self._memories.get(memory_id)

    def search(self, query: str) -> List[Memory]:
        return [m for m in self._memories.values() if m.matches_query(query)]

    def delete(self, memory_id: str) -> bool:
        if memory_id in self._memories:
            del self._memories[memory_id]
            return True
        return False

    def all(self) -> List[Memory]:
        return list(self._memories.values())