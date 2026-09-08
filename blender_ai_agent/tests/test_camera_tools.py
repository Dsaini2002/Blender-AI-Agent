from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.camera_tools import (
    CreateCameraTool,
    RenderPreviewTool,
    SetCameraTool,
)
from .fakes import FakeBridge, FakeObject


class TestCreateCameraTool(unittest.TestCase):

    def test_create_camera_success(self):
        bridge = FakeBridge()
        tool = CreateCameraTool(bridge)

        result = tool.execute({"name": "MainCamera"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["name"], "MainCamera")
        self.assertIsNotNone(bridge.get_object("MainCamera"))

    def test_create_camera_with_location(self):
        bridge = FakeBridge()
        tool = CreateCameraTool(bridge)

        result = tool.execute({"name": "MainCamera", "location": [0, -5, 2]})

        self.assertEqual(result.data["location"], [0, -5, 2])

    def test_invalid_location_length_fails(self):
        bridge = FakeBridge()
        tool = CreateCameraTool(bridge)

        result = tool.execute({"name": "MainCamera", "location": [0, -5]})

        self.assertFalse(result.success)


class TestSetCameraTool(unittest.TestCase):

    def test_set_camera_success(self):
        camera = FakeObject(name="MainCamera", type_="CAMERA")
        bridge = FakeBridge(objects=[camera])
        tool = SetCameraTool(bridge)

        result = tool.execute({"name": "MainCamera"})

        self.assertTrue(result.success)
        self.assertEqual(bridge._active_camera.name, "MainCamera")

    def test_set_missing_camera_fails_gracefully(self):
        bridge = FakeBridge(objects=[])
        tool = SetCameraTool(bridge)

        result = tool.execute({"name": "DoesNotExist"})

        self.assertFalse(result.success)

    def test_set_non_camera_object_fails(self):
        cube = FakeObject(name="Cube", type_="MESH")
        bridge = FakeBridge(objects=[cube])
        tool = SetCameraTool(bridge)

        result = tool.execute({"name": "Cube"})

        self.assertFalse(result.success)


class TestRenderPreviewTool(unittest.TestCase):

    def test_render_preview_returns_filepath(self):
        bridge = FakeBridge()
        tool = RenderPreviewTool(bridge)

        result = tool.execute({"filepath": "/tmp/preview.png"})

        self.assertTrue(result.success)
        self.assertEqual(result.data["filepath"], "/tmp/preview.png")

    def test_empty_filepath_fails_validation(self):
        bridge = FakeBridge()
        tool = RenderPreviewTool(bridge)

        result = tool.execute({"filepath": ""})

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()