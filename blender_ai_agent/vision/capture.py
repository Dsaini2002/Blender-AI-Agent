"""
Capture classes — Step 5.2
==============================
Hinglish: Blender-specific "screenshot lena" ka logic yahan encapsulate
hai — jaisa BlenderBridge raw bpy calls ko encapsulate karta hai.

Real Blender mein `render.preview` (Phase 2 ka tool) already render
lene ka kaam karta hai — ye classes usi capability ko VISION SYSTEM
ke liye ek clean, purpose-specific interface degi.
"""

from abc import ABC, abstractmethod


class Capture(ABC):
    """Har capture strategy (viewport/render/camera) isko extend karega."""

    @abstractmethod
    def capture(self, filepath: str) -> str:
        """Image ko `filepath` par save karta hai, wahi path return karta hai."""
        raise NotImplementedError


class RenderCapture(Capture):
    """Hinglish: Full render leta hai — BlenderBridge.render_preview() use karke."""

    def __init__(self, bridge):
        self._bridge = bridge

    def capture(self, filepath: str) -> str:
        return self._bridge.render_preview(filepath)


class ViewportCapture(Capture):
    """
    Hinglish: Abhi ke liye ViewportCapture bhi render_preview() use
    karta hai — real Blender mein viewport screenshot ke liye alag
    bpy.ops.screen.screenshot ya OpenGL render API chahiye hoga, jo
    hum BlenderBridge mein future mein add karenge. Abhi interface
    consistent rakhna zaroori hai — dono Capture types available
    hain, chahe andar ka implementation abhi same ho.
    """

    def __init__(self, bridge):
        self._bridge = bridge

    def capture(self, filepath: str) -> str:
        return self._bridge.render_preview(filepath)


class CameraCapture(Capture):
    """Hinglish: Ek specific camera se capture — pehle camera set karta hai, phir render leta hai."""

    def __init__(self, bridge):
        self._bridge = bridge

    def capture(self, filepath: str, camera_name: str = None) -> str:
        if camera_name is not None:
            self._bridge.set_active_camera(camera_name)
        return self._bridge.render_preview(filepath)