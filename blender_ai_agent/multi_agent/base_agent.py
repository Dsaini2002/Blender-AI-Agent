"""SpecializedAgent (base)"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentTaskResult:
    success: bool
    domain: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


class SpecializedAgent(ABC):
    domain: str = ""

    def __init__(self, tool_caller):
        self._tool_caller = tool_caller

    @abstractmethod
    def can_handle(self, subtask_description: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def execute(self, subtask_description: str, context: Dict[str, Any]) -> AgentTaskResult:
        raise NotImplementedError   