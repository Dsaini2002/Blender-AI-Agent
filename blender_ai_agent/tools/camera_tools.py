"""Camera / Render Tools"""

from ..image_paths import describe_image
from .base import Permission, Tool, ToolResult
from .models import CreateCameraInput, RenderPreviewInput, SetCameraInput


class CreateCameraTool(Tool):
    name = "camera.create"
    auto_name = "Camera"
    description = ("Creates a camera (or, if a camera with this name exists, moves that one) and makes it the active "
                   "render camera.")
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
        # The camera just placed is the one meant for the render: make it active (a later camera.set with the
        # old name used to keep rendering from the default camera).
        active = False
        set_active = getattr(self._bridge, "set_active_camera", None)
        if callable(set_active):
            try:
                active = bool(set_active(camera.name))
            except Exception:  # noqa: BLE001
                active = False
        return ToolResult.ok({
            "name": camera.name,
            "location": list(camera.location),
            "active": active,
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
        "By default this is a FAST preview (EEVEE, 16 samples, 960x540) so Blender does not freeze; draft=true makes "
        "it 640x360. final=true renders with the scene's own engine and settings (Cycles can take minutes and "
        "blocks Blender) - only when the user asks for the final render. The automatic check already renders the "
        "result, so you rarely need this at all."
    )
    permission = Permission.SAFE_WRITE
    input_model = RenderPreviewInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: RenderPreviewInput) -> ToolResult:
        kwargs = {}
        resolution = validated_input.resolution()
        if resolution is not None:
            kwargs["resolution"] = resolution

        if not validated_input.final:
            kwargs["fast"] = True
        try:
            path = self._bridge.render_preview(validated_input.filepath, **kwargs)
        except TypeError:                      # an older bridge without the `fast` option
            kwargs.pop("fast", None)
            path = self._bridge.render_preview(validated_input.filepath, **kwargs)

        data = {"filepath": path}
        data.update(describe_image(path))
        return ToolResult.ok(data)