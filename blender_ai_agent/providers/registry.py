"""
ProviderRegistry — Step 10.3
=================================
Hinglish: Phase 3 mein ModelProvider abstraction bana tha (ek
provider). Ab ye REGISTRY hai — jaisa ToolRegistry, sirf providers
ke liye. Naye providers (OpenAI, Anthropic, Local) add karne ke
liye Agent ka code kabhi nahi badalta — sirf registry mein register
hote hain (Open/Closed Principle).
"""

from typing import Callable, Dict

from .base import ModelProvider


class ProviderRegistry:

    def __init__(self):
        self._factories: Dict[str, Callable[..., ModelProvider]] = {}

    def register(self, name: str, factory: Callable[..., ModelProvider]) -> None:
        """
        Hinglish: `factory` ek callable hai jo ModelProvider instance
        banata hai (class khud, ya ek function) — taaki construction
        logic (API key padhna, etc.) registry ke bahar customize ho sake.
        """
        if name in self._factories:
            raise ValueError(f"Provider '{name}' already registered.")
        self._factories[name] = factory

    def create(self, name: str, **kwargs) -> ModelProvider:
        if name not in self._factories:
            raise KeyError(f"Provider '{name}' not found in registry.")
        return self._factories[name](**kwargs)

    def list_providers(self) -> list:
        return list(self._factories.keys())