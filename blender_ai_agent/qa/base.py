"""
Inspector (abstract base class) — Step 12.2
================================================
Hinglish: Jaise `Tool(ABC)` har tool ka contract fix karta hai, waise
hi `Inspector(ABC)` har QA-checker ka contract fix karta hai:
`inspect(bridge) -> List[Issue]`. Har concrete Inspector (geometry,
future UV/materials/animation) isko extend karega — yahi POLYMORPHISM
hai, jaisa baaki codebase mein already use ho raha hai.
"""

from abc import ABC, abstractmethod
from typing import List

from .models import Issue


class Inspector(ABC):
    """Har concrete Inspector (GeometryInspector, etc.) isko extend karega."""

    name: str = ""
    description: str = ""

    def __init__(self, bridge):
        # Dependency Injection — jaisa SceneInspector mein bridge pass hoti hai.
        self._bridge = bridge

    @abstractmethod
    def inspect(self) -> List[Issue]:
        """
        Hinglish: Scene ko check karke detected issues ki list deta hai.
        Koi issue nahi mili toh empty list — crash ya exception nahi.
        """
        raise NotImplementedError
