"""Memory models"""

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
        return query.lower() in self.content.lower()


@dataclass
class UserPreference(Memory):
    """Example: 'User prefers wood materials for furniture.'"""
    type: str = "user_preference"


@dataclass
class ProjectMemory(Memory):
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

_TYPES = {"generic": Memory, "user_preference": UserPreference, "project_memory": ProjectMemory, "task_memory": TaskMemory}


def to_dict(memory: Memory) -> Dict[str, Any]:
    data = {"id": memory.id, "type": memory.type, "content": memory.content, "metadata": dict(memory.metadata),
            "created_at": memory.created_at}
    if isinstance(memory, ProjectMemory):
        data["project_id"] = memory.project_id
    return data


def from_dict(data: Dict[str, Any]) -> Memory:
    cls = _TYPES.get(data.get("type", "generic"), Memory)
    kwargs = {"content": data["content"], "metadata": dict(data.get("metadata") or {}),
              "id": data.get("id") or str(uuid.uuid4())[:8], "created_at": data.get("created_at") or datetime.now().isoformat()}
    if cls is ProjectMemory:
        kwargs["project_id"] = data.get("project_id") or "unsaved"
    return cls(**kwargs)
