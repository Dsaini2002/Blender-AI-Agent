"""MemoryContextBuilder
====================

    MemoryStore -> Retriever -> MemoryContextBuilder -> Agent
"""

from dataclasses import dataclass, field
from typing import Dict, List

from .retriever import MemoryRetriever


@dataclass
class MemoryContext:
    by_type: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return len(self.by_type) == 0

    def render_text(self) -> str:
        if self.is_empty:
            return "No relevant memory."

        lines = []
        for mem_type, contents in self.by_type.items():
            lines.append(f"{mem_type}:")
            for content in contents:
                lines.append(f"- {content}")
        return "\n".join(lines)


class MemoryContextBuilder:

    def __init__(self, retriever: MemoryRetriever):
        self._retriever = retriever

    def build_context(self, query: str, limit: int = 5) -> MemoryContext:
        memories = self._retriever.retrieve(query, limit=limit)

        by_type: Dict[str, List[str]] = {}
        for mem in memories:
            by_type.setdefault(mem.type, []).append(mem.content)

        return MemoryContext(by_type=by_type)