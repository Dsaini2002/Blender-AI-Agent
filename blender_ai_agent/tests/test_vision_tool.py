from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.vision.analyzer import VisionAnalyzer
from blender_ai_agent.vision.capture import RenderCapture
from blender_ai_agent.vision.models import VisualObservation
from blender_ai_agent.vision.providers.mock import MockVisionProvider
from blender_ai_agent.vision.tool import VisionObserveTool
from .fakes import FakeBridge


def build_vision_tool(observations):
    bridge = FakeBridge()
    capture = RenderCapture(bridge)
    provider = MockVisionProvider(observations=observations)
    analyzer = VisionAnalyzer(capture, provider)
    return VisionObserveTool(analyzer), bridge, provider


class TestVisionObserveInput(unittest.TestCase):

    def test_invalid_source_raises(self):
        from blender_ai_agent.vision.tool import VisionObserveInput
        with self.assertRaises(ValueError):
            VisionObserveInput(source="telepathy")

    def test_valid_defaults(self):
        from blender_ai_agent.vision.tool import VisionObserveInput
        input_ = VisionObserveInput()
        self.assertEqual(input_.source, "render")


class TestVisionObserveTool(unittest.TestCase):

    def test_returns_observation_data(self):
        tool, _, _ = build_vision_tool(observations=[
            VisualObservation(
                description="A red cube on a plane.",
                objects_detected=["cube", "plane"],
                confidence=0.9,
            )
        ])

        result = tool.execute({"source": "render", "filepath": "/tmp/test.png"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["description"], "A red cube on a plane.")
        self.assertIn("cube", result.data["objects_detected"])
        self.assertEqual(result.data["confidence"], 0.9)

    def test_permission_is_read_only(self):
        tool, _, _ = build_vision_tool(observations=[VisualObservation(description="x")])
        from blender_ai_agent.tools.base import Permission
        self.assertEqual(tool.permission, Permission.READ_ONLY)

    def test_invalid_source_fails_validation(self):
        tool, _, _ = build_vision_tool(observations=[VisualObservation(description="x")])

        result = tool.execute({"source": "invalid"})

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()