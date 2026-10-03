"""
Camera / Render Tools — Step 2.7
===================================
Hinglish: Same pattern. RenderPreviewTool khaas hai kyunki iska
output ek IMAGE FILE hai — ye Phase 5 (Vision) ke liye foundation hai.

Advanced: render ab (1) "draft" / width / height se chhota-tez preview le sakta hai (vision check ke liye
kaafi hai, aur jaldi hota hai), aur (2) result mein file ka saboot deta hai (size + pixel) jab file asal mein
ban gayi ho.
"""

from ..image_paths import describe_image
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
    description = (
        "Renders the current scene and saves it to an image file. Use a plain file name like "
        "'room_preview.png' (any folder you give is ignored on Windows; the file goes to the temp folder). "
        "The result's `filepath` is the real saved path - pass exactly that to vision.observe. "
        "Optional: draft=true for a fast small 640x360 preview (enough for a visual check), or width/height "
        "in pixels. When the file was really written the result also shows size_bytes and width/height."
    )
    permission = Permission.SAFE_WRITE
    input_model = RenderPreviewInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: RenderPreviewInput) -> ToolResult:
        # Hinglish: resolution tabhi bhejte hain jab maangi gayi ho — purana bridge/fake bina badlaav chalta rahe.
        kwargs = {}
        resolution = validated_input.resolution()
        if resolution is not None:
            kwargs["resolution"] = resolution

        path = self._bridge.render_preview(validated_input.filepath, **kwargs)

        data = {"filepath": path}
        data.update(describe_image(path))
        return ToolResult.ok(data)