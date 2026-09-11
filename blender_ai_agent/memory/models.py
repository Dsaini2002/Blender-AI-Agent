"""
Memory models — Step 7.3
============================
Hinglish: Har memory ek typed object hai — random dict nahi. Base
`Memory` class common fields define karti hai; concrete subclasses
(UserPreference, ProjectMemory, TaskMemory) specific context add
karte hain — Inheritance + Polymorphism.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict


@dataclass
class Memory:
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "generic"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        if not self.content or not isinstance(self.content, str):
            raise ValueError(f"{type(self).__name__}.content must be a non-empty string")

    def matches_query(self, query: str) -> bool:
        """
        Hinglish: Base relevance check — abhi simple substring match.
        Concrete memory types isko override kar sakte hain agar unhe
        alag matching logic chahiye (Polymorphism).
        """
        return query.lower() in self.content.lower()


@dataclass
class UserPreference(Memory):
    """Example: 'User prefers wood materials for furniture.'"""
    type: str = "user_preference"


@dataclass
class ProjectMemory(Memory):
    """
    Hinglish: `project_id` zaroori hai — Step 7.18 ka rule: alag
    projects ki memory mix nahi honi chahiye.
    """
    type: str = "project_memory"
    project_id: str = ""

    def __post_init__(self):
        super().__post_init__()
        if not self.project_id:
            raise ValueError("ProjectMemory.project_id must not be empty")


@dataclass
class TaskMemory(Memory):
    """Example: 'Created spaceship with bevel + metallic material.'"""
    type: str = "task_memory"