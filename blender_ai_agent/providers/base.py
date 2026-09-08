"""
ModelProvider (abstract base class) — Step 3.1
==================================================
Hinglish: Ye Phase 3 ka sabse important abstraction hai.

Agent kisi ek AI company (OpenAI, Anthropic, etc.) se TIGHTLY COUPLE
nahi hoga. Agent sirf itna jaanega:

    provider.generate(request) -> ModelResponse

Andar OpenAI hai ya Anthropic ya ek fake/mock provider — Agent ko
fark nahi padega. Ye Dependency Inversion Principle hai: Agent ek
high-level module hai, aur wo kisi low-level detail (OpenAI ka SDK)
par depend nahi karta — dono ek shared abstraction (ModelProvider) par
depend karte hain.
"""

from abc import ABC, abstractmethod


class ModelProvider(ABC):
    """
    Har concrete provider (OpenAIProvider, AnthropicProvider,
    MockProvider) isko extend karega aur `generate()` implement karega.
    """

    @abstractmethod
    def generate(self, request):
        """
        Hinglish: `request` ek ModelRequest object hoga (Step 3.2 mein
        banayenge), aur return value ek ModelResponse hoga.

        Abhi Step 3.1 mein hum sirf contract define kar rahe hain —
        real request/response types Step 3.2 mein aayenge.
        """
        raise NotImplementedError