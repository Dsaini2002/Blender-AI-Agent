from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.vision.capture import CameraCapture, RenderCapture, ViewportCapture
from .fakes import FakeBridge, FakeObject


class TestRenderCapture(unittest.TestCase):

    def test_capture_returns_filepath(self):
        bridge = FakeBridge()
        capture = RenderCapture(bridge)

        result = capture.capture("/tmp/render.png")

        self.assertEqual(result, "/tmp/render.png")
        self.assertEqual(bridge._last_render_path, "/tmp/render.png")


class TestViewportCapture(unittest.TestCase):

    def test_capture_returns_filepath(self):
        bridge = FakeBridge()
        capture = ViewportCapture(bridge)

        result = capture.capture("/tmp/viewport.png")

        self.assertEqual(result, "/tmp/viewport.png")


class TestCameraCapture(unittest.TestCase):

    def test_capture_sets_camera_then_renders(self):
        camera = FakeObject(name="Camera.001", type_="CAMERA")
        bridge = FakeBridge(objects=[camera])
        capture = CameraCapture(bridge)

        result = capture.capture("/tmp/cam.png", camera_name="Camera.001")

        self.assertEqual(result, "/tmp/cam.png")
        self.assertEqual(bridge._active_camera.name, "Camera.001")

    def test_capture_without_camera_name_just_renders(self):
        bridge = FakeBridge()
        capture = CameraCapture(bridge)

        result = capture.capture("/tmp/cam.png")

        self.assertEqual(result, "/tmp/cam.png")


if __name__ == "__main__":
    unittest.main()