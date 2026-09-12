from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.providers.mock_provider import MockProvider
from blender_ai_agent.providers.registry import ProviderRegistry


class TestProviderRegistry(unittest.TestCase):

    def test_register_and_create(self):
        registry = ProviderRegistry()
        registry.register("mock", lambda **kwargs: MockProvider(**kwargs))

        provider = registry.create("mock", responses=["hello"])

        self.assertIsInstance(provider, MockProvider)

    def test_duplicate_register_raises(self):
        registry = ProviderRegistry()
        registry.register("mock", lambda **kwargs: MockProvider())

        with self.assertRaises(ValueError):
            registry.register("mock", lambda **kwargs: MockProvider())

    def test_create_unknown_provider_raises(self):
        registry = ProviderRegistry()

        with self.assertRaises(KeyError):
            registry.create("does-not-exist")

    def test_list_providers(self):
        registry = ProviderRegistry()
        registry.register("mock", lambda **kwargs: MockProvider())
        registry.register("fake2", lambda **kwargs: MockProvider())

        self.assertEqual(set(registry.list_providers()), {"mock", "fake2"})


if __name__ == "__main__":
    unittest.main()