from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.suggestions import SuggestionEngine
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge, FakeObject


def build_engine(objects):
    bridge = FakeBridge(objects=objects)
    inspector = SceneInspector(bridge)
    tool = SceneInspectTool(inspector)
    return SuggestionEngine(tool)


class TestSuggestionEngine(unittest.TestCase):

    def test_empty_scene_suggests_create_object(self):
        engine = build_engine(objects=[])
        suggestions = engine.suggest()

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].action, "object.create")

    def test_scene_without_camera_suggests_camera(self):
        engine = build_engine(objects=[FakeObject(name="Cube")])
        suggestions = engine.suggest()

        actions = [s.action for s in suggestions]
        self.assertIn("camera.create", actions)

    def test_scene_with_camera_suggests_framing_check(self):
        engine = build_engine(objects=[FakeObject(name="Cube"), FakeObject(name="Camera", type_="CAMERA")])
        suggestions = engine.suggest()

        actions = [s.action for s in suggestions]
        self.assertIn("vision.observe", actions)
        self.assertNotIn("camera.create", actions)

    def test_suggestion_has_title(self):
        engine = build_engine(objects=[FakeObject(name="Cube")])
        suggestions = engine.suggest()

        self.assertTrue(all(s.title for s in suggestions))


if __name__ == "__main__":
    unittest.main()