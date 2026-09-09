"""
VisionProvider (abstract base class) — Step 5.1 / 5.13
===========================================================
Hinglish: EXACT same pattern jo Phase 3 ka ModelProvider follow karta
hai. Agent (ya VisionAnalyzer) ko ye nahi pata hoga ki andar OpenAI
Vision hai, Anthropic hai, local model hai, ya Mock — sirf itna:

    provider.analyze(image, context) -> VisualObservation

Dependency Inversion — high-level code (Agent) low-level detail
(specific vision API) par depend nahi karta.
"""

from abc import ABC, abstractmethod


class VisionProvider(ABC):

    @abstractmethod
    def analyze(self, image, context):
        """
        Hinglish: `image` abhi ke liye ek filepath (string) hoga —
        real capture (Step 5.2) isko produce karega. `context` ek
        dict hoga (scene state ka relevant hissa — Step 5.14).

        Return: VisualObservation
        """
        raise NotImplementedError