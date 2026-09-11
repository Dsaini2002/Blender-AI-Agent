from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.context import CopilotContextBuilder
from .fakes import FakeBridge, FakeObject


class TestCopilotContextBuilder(unittest.TestCase):

    def test_no_selection_means_no_active_object(self):
        bridge = FakeBridge()
        builder = CopilotContextBuilder(bridge)

        context = builder.build()

        self.assertEqual(context.selected_objects, [])
        self.assertIsNone(context.active_object)

    def test_selection_sets_active_object(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        builder = CopilotContextBuilder(bridge)

        context = builder.build(selected_object_names=["Cube"])

        self.assertEqual(context.active_object, "Cube")
        self.assertEqual(context.selected_objects, ["Cube"])

    def test_finds_active_camera(self):
        bridge = FakeBridge(objects=[FakeObject(name="Camera.001", type_="CAMERA")])
        builder = CopilotContextBuilder(bridge)

        context = builder.build()

        self.assertEqual(context.active_camera, "Camera.001")

    def test_no_camera_in_scene(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube")])
        builder = CopilotContextBuilder(bridge)

        context = builder.build()

        self.assertIsNone(context.active_camera)

    def test_includes_scene_name(self):
        bridge = FakeBridge(scene_name="MyScene")
        builder = CopilotContextBuilder(bridge)

        context = builder.build()

        self.assertEqual(context.current_scene, "MyScene")


if __name__ == "__main__":
    unittest.main()