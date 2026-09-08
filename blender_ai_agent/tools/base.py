"""
Tool (abstract base class)
===========================
Hinglish: Ye har "deterministic tool" ka common contract/interface hai.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class Tool(ABC):
    name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Har concrete tool ye method implement karega. ABC ki wajah se
        agar koi subclass isko implement nahi karega, Python khud
        error de dega.
        """
        raise NotImplementedError