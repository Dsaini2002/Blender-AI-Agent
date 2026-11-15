"""Tracer
======

    Task
     ├── Planning
     ├── Skill selection
     ├── Modeling
     │    ├── Tool 1
     │    ├── Tool 2
     │    └── Tool 3
     ├── Material
     ├── Camera
     └── Validation
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TraceSpan:
    name: str
    children: List["TraceSpan"] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class Tracer:

    def __init__(self):
        self._root_spans: List[TraceSpan] = []
        self._stack: List[TraceSpan] = []

    def start_span(self, name: str, **metadata) -> TraceSpan:
        span = TraceSpan(name=name, metadata=metadata)

        if self._stack:
            self._stack[-1].children.append(span)
        else:
            self._root_spans.append(span)

        self._stack.append(span)
        return span

    def end_span(self) -> None:
        if self._stack:
            self._stack.pop()

    def get_trace(self) -> List[TraceSpan]:
        return list(self._root_spans)

    def render_tree(self) -> str:
        lines = []
        for span in self._root_spans:
            self._render_span(span, depth=0, lines=lines)
        return "\n".join(lines)

    def _render_span(self, span: TraceSpan, depth: int, lines: List[str]) -> None:
        lines.append("  " * depth + span.name)
        for child in span.children:
            self._render_span(child, depth + 1, lines)