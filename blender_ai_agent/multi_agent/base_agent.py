"""
SpecializedAgent (base) — Step 11.11
=========================================
Hinglish: Har specialized agent ek "domain" ka expert hai — modeling,
material, camera, etc. Sab same interface follow karte hain
(Polymorphism), taaki Supervisor unhe uniform tarike se call kare.
"""

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
        # Dependency Injection — jaisa hamesha
        self._tool_caller = tool_caller

    @abstractmethod
    def can_handle(self, subtask_description: str) -> bool:
        """Hinglish: Ye subtask is agent ke domain mein aata hai?"""
        raise NotImplementedError

    @abstractmethod
    def execute(self, subtask_description: str, context: Dict[str, Any]) -> AgentTaskResult:
        raise NotImplementedError   