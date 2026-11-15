"""MemoryRetriever"""

from dataclasses import dataclass
from typing import List

from .models import Memory
from .store import MemoryStore


@dataclass
class ScoredMemory:
    memory: Memory
    relevance: float


class MemoryRetriever:

    def __init__(self, store: MemoryStore, threshold: float = 0.3):
        self._store = store
        self._threshold = threshold

    def retrieve(self, query: str, limit: int = 5) -> List[Memory]:
        scored = self._score_all(query)
        relevant = [s for s in scored if s.relevance >= self._threshold]
        relevant.sort(key=lambda s: s.relevance, reverse=True)
        return [s.memory for s in relevant[:limit]]

    def score(self, query: str, memory: Memory) -> float:
        query_words = set(self._normalize(query).split())
        content_words = set(self._normalize(memory.content).split())

        if not query_words:
            return 0.0

        overlap = query_words & content_words
        return len(overlap) / len(query_words)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _score_all(self, query: str) -> List[ScoredMemory]:
        all_memories = self._store.search("") if hasattr(self._store, "all") is False else self._store.all()
        return [ScoredMemory(memory=m, relevance=self.score(query, m)) for m in all_memories]

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(ch if ch.isalnum() else " " for ch in text.lower())