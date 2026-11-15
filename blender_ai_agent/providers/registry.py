"""ProviderRegistry"""

from typing import Callable, Dict

from .base import ModelProvider


class ProviderRegistry:

    def __init__(self):
        self._factories: Dict[str, Callable[..., ModelProvider]] = {}

    def register(self, name: str, factory: Callable[..., ModelProvider]) -> None:
        if name in self._factories:
            raise ValueError(f"Provider '{name}' already registered.")
        self._factories[name] = factory

    def create(self, name: str, **kwargs) -> ModelProvider:
        if name not in self._factories:
            raise KeyError(f"Provider '{name}' not found in registry.")
        return self._factories[name](**kwargs)

    def list_providers(self) -> list:
        return list(self._factories.keys())