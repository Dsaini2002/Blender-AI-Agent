"""VisionProvider (abstract base class)
====================================

    provider.analyze(image, context) -> VisualObservation
"""

from abc import ABC, abstractmethod


class VisionProvider(ABC):

    @abstractmethod
    def analyze(self, image, context):
        """Return: VisualObservation"""
        raise NotImplementedError