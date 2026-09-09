from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from blender_ai_agent.vision.analyzer import VisionAnalyzer
from blender_ai_agent.vision.capture import RenderCapture
from blender_ai_agent.vision.context import VisionContextManager
from blender_ai_agent.vision.models import VisualObservation
from blender_ai_agent.vision.providers.mock import MockVisionProvider
from .fakes import FakeBridge, FakeObject


def build_vision_context_manager(observations, objects=None):
    bridge = FakeBridge(objects=objects or [])
    inspector = SceneInspector(bridge)
    scene_tool = SceneInspectTool(inspector)
    context_manager = ContextManager(scene_tool)

    capture = RenderCapture(bridge)
    provider = MockVisionProvider(observations=observations)
    analyzer = VisionAnalyzer(capture, provider)

    return VisionContextManager(context_manager, analyzer)


class TestVisionContextManager(unittest.TestCase):

    def test_combines_scene_and_visual_data(self):
        cube = FakeObject(name="Cube")
        vcm = build_vision_context_manager(
            observations=[VisualObservation(description="A cube.", objects_detected=["cube"])],
            objects=[cube],
        )

        result = vcm.build_context(filepath="/tmp/test.png")

        self.assertTrue(result.has_visual_data())
        self.assertEqual(result.scene_context["object_count"], 1)
        self.assertEqual(result.visual_observation.description, "A cube.")

    def test_empty_scene_still_gets_visual_observation(self):
        vcm = build_vision_context_manager(
            observations=[VisualObservation(description="Empty scene.")],
            objects=[],
        )

        result = vcm.build_context(filepath="/tmp/empty.png")

        self.assertEqual(result.scene_context["object_count"], 0)
        self.assertEqual(result.visual_observation.description, "Empty scene.")


if __name__ == "__main__":
    unittest.main()