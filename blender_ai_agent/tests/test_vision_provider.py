from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.vision.models import VisualObservation
from blender_ai_agent.vision.providers.base import VisionProvider
from blender_ai_agent.vision.providers.mock import MockVisionProvider


class TestVisualObservation(unittest.TestCase):

    def test_valid_observation(self):
        obs = VisualObservation(description="A red cube on a plane.", confidence=0.9)
        self.assertEqual(obs.description, "A red cube on a plane.")
        self.assertFalse(obs.is_low_confidence)

    def test_invalid_confidence_raises(self):
        with self.assertRaises(ValueError):
            VisualObservation(description="test", confidence=1.5)

    def test_low_confidence_flagged(self):
        obs = VisualObservation(description="unclear", confidence=0.3)
        self.assertTrue(obs.is_low_confidence)

    def test_defaults(self):
        obs = VisualObservation(description="empty scene")
        self.assertEqual(obs.objects_detected, [])
        self.assertEqual(obs.issues, [])
        self.assertEqual(obs.confidence, 1.0)


class TestVisionProviderBase(unittest.TestCase):

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            VisionProvider()

    def test_subclass_without_analyze_fails(self):
        class BrokenProvider(VisionProvider):
            pass

        with self.assertRaises(TypeError):
            BrokenProvider()


class TestMockVisionProvider(unittest.TestCase):

    def test_returns_scripted_observation(self):
        obs = VisualObservation(description="a cube")
        provider = MockVisionProvider(observations=[obs])

        result = provider.analyze("fake_image.png", {})

        self.assertEqual(result.description, "a cube")

    def test_tracks_received_calls(self):
        provider = MockVisionProvider(observations=[VisualObservation(description="x")])
        provider.analyze("image.png", {"camera": "Camera.001"})

        self.assertEqual(provider.received_calls[0], ("image.png", {"camera": "Camera.001"}))

    def test_raises_when_observations_exhausted(self):
        provider = MockVisionProvider(observations=[VisualObservation(description="only_one")])
        provider.analyze("img1.png", {})

        with self.assertRaises(RuntimeError):
            provider.analyze("img2.png", {})


if __name__ == "__main__":
    unittest.main()