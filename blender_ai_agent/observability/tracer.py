"""
Tracer — Step 9.34
======================
Hinglish: Phase 4 ka Logger flat events rakhta tha. Ye Tracer NESTED
structure banata hai — task -> subtask -> tool_calls — jaisa spec
ka example:

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
    """Hinglish: Ek single named operation, jisme child spans ho sakte hain."""
    name: str
    children: List["TraceSpan"] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class Tracer:

    def __init__(self):
        self._root_spans: List[TraceSpan] = []
        self._stack: List[TraceSpan] = []

    def start_span(self, name: str, **metadata) -> TraceSpan:
        """Hinglish: Naya span shuru karta hai — agar koi parent active hai, uska child banta hai."""
        span = TraceSpan(name=name, metadata=metadata)

        if self._stack:
            self._stack[-1].children.append(span)
        else:
            self._root_spans.append(span)

        self._stack.append(span)
        return span

    def end_span(self) -> None:
        """Hinglish: Current active span ko close karta hai (stack se pop)."""
        if self._stack:
            self._stack.pop()

    def get_trace(self) -> List[TraceSpan]:
        return list(self._root_spans)

    def render_tree(self) -> str:
        """Hinglish: Spec ke example jaisa indented tree view."""
        lines = []
        for span in self._root_spans:
            self._render_span(span, depth=0, lines=lines)
        return "\n".join(lines)

    def _render_span(self, span: TraceSpan, depth: int, lines: List[str]) -> None:
        lines.append("  " * depth + span.name)
        for child in span.children:
            self._render_span(child, depth + 1, lines)