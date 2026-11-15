"""Inspector (abstract base class)"""

from abc import ABC, abstractmethod
from typing import List

from .models import Issue


class Inspector(ABC):

    name: str = ""
    description: str = ""

    def __init__(self, bridge):
        self._bridge = bridge

    @abstractmethod
    def inspect(self) -> List[Issue]:
        raise NotImplementedError
