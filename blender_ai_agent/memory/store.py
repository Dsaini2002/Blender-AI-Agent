"""MemoryStore"""

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

class JsonFileStore(InMemoryStore):
    """Memories that survive Blender restarts: kept in a small JSON file (default ~/BlenderAIAgent/memory.json).
    The oldest task memories are dropped once `max_items` is reached; preferences are kept."""

    def __init__(self, path: str, max_items: int = 400):
        super().__init__()
        self._path = path
        self._max_items = max_items
        self._load()

    @property
    def path(self) -> str:
        return self._path

    def save(self, memory: Memory) -> None:
        super().save(memory)
        self._trim()
        self._write()

    def delete(self, memory_id: str) -> bool:
        removed = super().delete(memory_id)
        if removed:
            self._write()
        return removed

    def clear(self) -> None:
        self._memories.clear()
        self._write()

    def _trim(self) -> None:
        if len(self._memories) <= self._max_items:
            return
        removable = sorted((m for m in self._memories.values() if m.type != "user_preference"), key=lambda m: m.created_at)
        for memory in removable[: len(self._memories) - self._max_items]:
            del self._memories[memory.id]

    def _load(self) -> None:
        import json
        import os
        from .models import from_dict
        if not os.path.isfile(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return
        for item in data.get("memories", []) if isinstance(data, dict) else []:
            try:
                memory = from_dict(item)
            except (TypeError, ValueError, KeyError):
                continue
            self._memories[memory.id] = memory

    def _write(self) -> None:
        import json
        import os
        from .models import to_dict
        try:
            folder = os.path.dirname(self._path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as handle:
                json.dump({"version": 1, "memories": [to_dict(m) for m in self._memories.values()]}, handle, indent=1)
            os.replace(tmp, self._path)
        except OSError:
            pass
