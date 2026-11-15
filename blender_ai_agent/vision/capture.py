"""Capture classes"""

from abc import ABC, abstractmethod


class Capture(ABC):

    @abstractmethod
    def capture(self, filepath: str) -> str:
        raise NotImplementedError


class RenderCapture(Capture):

    def __init__(self, bridge):
        self._bridge = bridge

    def capture(self, filepath: str) -> str:
        return self._bridge.render_preview(filepath)


class ViewportCapture(Capture):

    def __init__(self, bridge):
        self._bridge = bridge

    def capture(self, filepath: str) -> str:
        return self._bridge.render_preview(filepath)


class CameraCapture(Capture):

    def __init__(self, bridge):
        self._bridge = bridge

    def capture(self, filepath: str, camera_name: str = None) -> str:
        if camera_name is not None:
            self._bridge.set_active_camera(camera_name)
        return self._bridge.render_preview(filepath)