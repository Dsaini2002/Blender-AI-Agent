
import re
from typing import List

_BULLET = re.compile(r"^\s*(?:[-*\u2022]+|\d{1,2}[.)])\s+")
_INLINE_NUMBERS = re.compile(r"(?:(?<=\s)|^)\d{1,2}[.)]\s+")
_CONNECTORS = re.compile(
    r"\b(?:and\s+then|and\s+after\s+that|after\s+that|afterwards|then|aur\s+phir|uske\s+baad|phir)\b",
    re.IGNORECASE,
)
_SENTENCES = re.compile(r"(?<=[.!?])\s+(?=\S)|;\s*")
_ACTION_VERBS = (
    r"(?:create|make|add|build|place|put|set|move|rotate|scale|delete|remove|render|apply|import|rename|"
    r"duplicate|bevel|animate|paint|attach|connect|fix|change|generate|design|spawn|retopologize|analyze|"
    r"search|find|insert|extrude|subdivide|assign|resize|arrange)"
)
_VERB_SPLIT = re.compile(rf"\s*(?:,\s*(?:and\s+|aur\s+)?|\s+and\s+|\s+aur\s+)(?={_ACTION_VERBS}\b)", re.IGNORECASE)


def _clean(part: str) -> str:
    part = _BULLET.sub("", part)
    part = re.sub(r"^(?:and|aur|also|then|phir)\s+", "", part.strip(), flags=re.IGNORECASE)
    return part.strip(" \t\r\n,.;:!?-")


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text))


def _merge_tiny(parts: List[str], min_words: int = 2) -> List[str]:
    merged: List[str] = []
    for part in parts:
        if merged and _word_count(part) < min_words:
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    if len(merged) > 1 and _word_count(merged[0]) < min_words:
        merged[1] = f"{merged[0]} {merged[1]}"
        merged = merged[1:]
    return merged


def _cap(parts: List[str], max_parts: int) -> List[str]:
    if len(parts) <= max_parts:
        return parts
    size = -(-len(parts) // max_parts)                      # ceil
    return [" ".join(parts[i:i + size]) for i in range(0, len(parts), size)]


def split_task(text: str, min_parts: int = 3, max_parts: int = 10) -> List[str]:
    original = (text or "").strip()
    if not original:
        return []

    lines = [ln for ln in original.splitlines() if ln.strip()]
    if len(lines) >= 2:
        raw = lines
    elif len(_INLINE_NUMBERS.findall(original)) >= 2:
        raw = _INLINE_NUMBERS.split(original)
    else:
        pieces: List[str] = []
        for sentence in _SENTENCES.split(original):
            for chunk in _CONNECTORS.split(sentence):
                pieces.extend(_VERB_SPLIT.split(chunk))
        raw = pieces

    parts = _merge_tiny([c for c in (_clean(p) for p in raw) if c])
    if len(parts) < min_parts:
        return [original]
    return _cap(parts, max_parts)