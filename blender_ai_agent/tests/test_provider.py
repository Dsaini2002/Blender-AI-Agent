from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.providers.base import ModelProvider
from blender_ai_agent.providers.mock_provider import MockProvider


class TestModelProviderBase(unittest.TestCase):

    def test_cannot_instantiate_directly(self):
        """ModelProvider ek ABC hai — bina generate() implement kiye instantiate nahi ho sakta."""
        with self.assertRaises(TypeError):
            ModelProvider()

    def test_subclass_without_generate_fails(self):
        class BrokenProvider(ModelProvider):
            pass

        with self.assertRaises(TypeError):
            BrokenProvider()

    def test_valid_subclass_works(self):
        class EchoProvider(ModelProvider):
            def generate(self, request):
                return f"echo: {request}"

        provider = EchoProvider()
        self.assertEqual(provider.generate("hello"), "echo: hello")


class TestMockProvider(unittest.TestCase):

    def test_returns_scripted_responses_in_order(self):
        provider = MockProvider(responses=["first", "second"])

        self.assertEqual(provider.generate("req1"), "first")
        self.assertEqual(provider.generate("req2"), "second")

    def test_tracks_call_count(self):
        provider = MockProvider(responses=["only"])
        self.assertEqual(provider.call_count, 0)

        provider.generate("req1")
        self.assertEqual(provider.call_count, 1)

    def test_records_received_requests(self):
        provider = MockProvider(responses=["ok"])
        provider.generate("what was sent")

        self.assertEqual(provider.received_requests, ["what was sent"])

    def test_raises_when_responses_exhausted(self):
        provider = MockProvider(responses=["only_one"])
        provider.generate("req1")  # ye response consume kar leta hai

        with self.assertRaises(RuntimeError):
            provider.generate("req2")  # ab koi response bacha nahi

    def test_empty_responses_raises_on_first_call(self):
        provider = MockProvider()  # koi response scripted nahi

        with self.assertRaises(RuntimeError):
            provider.generate("anything")


if __name__ == "__main__":
    unittest.main()