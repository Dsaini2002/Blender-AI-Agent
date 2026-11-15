"""MemoryPolicy"""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from .models import Memory

_SECRET_PATTERNS = [
    re.compile(r"api[_-]?key", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"secret", re.IGNORECASE),
    re.compile(r"token", re.IGNORECASE),
    re.compile(r"credential", re.IGNORECASE),
]

_MIN_CONTENT_LENGTH = 5


class MemoryPolicy:

    def __init__(self, expiry_days: int = 90):
        self._expiry_days = expiry_days

    def should_store(self, content: str) -> bool:
        if len(content.strip()) < _MIN_CONTENT_LENGTH:
            return False
        if self._contains_secret(content):
            return False
        return True

    def should_retrieve(self, memory: Memory) -> bool:
        return not self.should_expire(memory)

    def should_expire(self, memory: Memory) -> bool:
        created = datetime.fromisoformat(memory.created_at)
        return datetime.now() - created > timedelta(days=self._expiry_days)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    @staticmethod
    def _contains_secret(content: str) -> bool:
        return any(pattern.search(content) for pattern in _SECRET_PATTERNS)