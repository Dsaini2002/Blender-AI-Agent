from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.vision.analyzer import VisionAnalyzer
from blender_ai_agent.vision.capture import RenderCapture
from blender_ai_agent.vision.models import VisualObservation
from blender_ai_agent.vision.providers.mock import MockVisionProvider
from blender_ai_agent.vision.tool import VisionObserveTool
from .fakes import FakeBridge


class TestVisionToolConfidenceWarning(unittest.TestCase):

    def test_low_confidence_flagged_in_result(self):
        bridge = FakeBridge()
        capture = RenderCapture(bridge)
        provider = MockVisionProvider(observations=[
            VisualObservation(description="unclear image", confidence=0.3)
        ])
        analyzer = VisionAnalyzer(capture, provider)
        tool = VisionObserveTool(analyzer)

        result = tool.execute({"filepath": "/tmp/test.png"})

        self.assertTrue(result.success)  # tool fail nahi hota
        self.assertTrue(result.data.get("low_confidence_warning"))

    def test_high_confidence_no_warning(self):
        bridge = FakeBridge()
        capture = RenderCapture(bridge)
        provider = MockVisionProvider(observations=[
            VisualObservation(description="clear cube", confidence=0.95)
        ])
        analyzer = VisionAnalyzer(capture, provider)
        tool = VisionObserveTool(analyzer)

        result = tool.execute({"filepath": "/tmp/test.png"})

        self.assertNotIn("low_confidence_warning", result.data)


if __name__ == "__main__":
    unittest.main()