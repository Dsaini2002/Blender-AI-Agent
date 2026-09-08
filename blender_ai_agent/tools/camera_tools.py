"""
Camera / Render Tools — Step 2.7
===================================
Hinglish: Same pattern. RenderPreviewTool khaas hai kyunki iska
output ek IMAGE FILE hai — ye Phase 5 (Vision) ke liye foundation hai.
"""

from .base import Permission, Tool, ToolResult
from .models import CreateCameraInput, RenderPreviewInput, SetCameraInput


class CreateCameraTool(Tool):
    name = "camera.create"
    description = "Creates a new camera object in the scene."
    permission = Permission.SAFE_WRITE
    input_model = CreateCameraInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: CreateCameraInput) -> ToolResult:
        camera = self._bridge.create_camera(
            name=validated_input.name,
            location=validated_input.location,
            rotation=validated_input.rotation,
        )
        return ToolResult.ok({
            "name": camera.name,
            "location": list(camera.location),
        })


class SetCameraTool(Tool):
    name = "camera.set"
    description = "Sets the scene's active (render) camera."
    permission = Permission.SAFE_WRITE
    input_model = SetCameraInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: SetCameraInput) -> ToolResult:
        success = self._bridge.set_active_camera(validated_input.name)

        if not success:
            return ToolResult.fail(
                f"Could not set '{validated_input.name}' as active camera — "
                "object not found or is not a camera."
            )

        return ToolResult.ok({"active_camera": validated_input.name})


class RenderPreviewTool(Tool):
    name = "render.preview"
    description = "Renders the current scene and saves it to a file."
    permission = Permission.SAFE_WRITE
    input_model = RenderPreviewInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: RenderPreviewInput) -> ToolResult:
        path = self._bridge.render_preview(validated_input.filepath)
        return ToolResult.ok({"filepath": path})