from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.vision.errors import (
    VisionError,
    VisionErrorCode,
    check_confidence,
    classify_vision_exception,
)
from blender_ai_agent.vision.models import VisualObservation


class TestClassifyVisionException(unittest.TestCase):

    def test_timeout_classified(self):
        error = classify_vision_exception(RuntimeError("Request timeout occurred"))
        self.assertEqual(error.code, VisionErrorCode.VISION_TIMEOUT)
        self.assertTrue(error.recoverable)

    def test_provider_failure_classified(self):
        error = classify_vision_exception(RuntimeError("no scripted observation left"))
        self.assertEqual(error.code, VisionErrorCode.VISION_PROVIDER_FAILED)

    def test_unrecognized_classified_as_provider_failed_not_recoverable(self):
        error = classify_vision_exception(RuntimeError("totally unexpected"))
        self.assertFalse(error.recoverable)


class TestCheckConfidence(unittest.TestCase):

    def test_sufficient_confidence_passes_silently(self):
        obs = VisualObservation(description="cube", confidence=0.9)
        check_confidence(obs, min_confidence=0.5)  # exception nahi aani chahiye

    def test_low_confidence_raises_vision_error(self):
        obs = VisualObservation(description="unclear", confidence=0.2)
        with self.assertRaises(VisionError) as ctx:
            check_confidence(obs, min_confidence=0.5)

        self.assertEqual(ctx.exception.code, VisionErrorCode.LOW_CONFIDENCE)


if __name__ == "__main__":
    unittest.main()