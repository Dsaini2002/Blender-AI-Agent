"""VisionObserveTool"""

import os
import tempfile
from dataclasses import dataclass, field

from ..image_paths import describe_image, resolve_image_path
from ..tools.base import Permission, Tool, ToolResult


def _default_vision_filepath() -> str:
    return os.path.join(tempfile.gettempdir(), "vision_observe.png")


@dataclass
class VisionObserveInput:
    source: str = "render"
    filepath: str = field(default_factory=_default_vision_filepath)

    def __post_init__(self):
        valid_sources = ("viewport", "render", "camera")
        if self.source not in valid_sources:
            raise ValueError(f"VisionObserveInput.source must be one of {valid_sources}, got '{self.source}'")
        if not self.filepath:
            raise ValueError("VisionObserveInput.filepath must be a non-empty string")


class VisionObserveTool(Tool):
    name = "vision.observe"
    description = (
        "Captures the current scene visually and returns a structured observation. Use a plain file name "
        "(or the exact `filepath` render.preview returned); any folder is ignored on Windows."
    )
    permission = Permission.READ_ONLY
    input_model = VisionObserveInput

    def __init__(self, analyzer):
        self._analyzer = analyzer

    def _observe(self, filepath: str, source: str):
        try:
            return self._analyzer.observe(filepath=filepath, context={"source": source})
        except FileNotFoundError:
            fallback = os.path.join(tempfile.gettempdir(), os.path.basename(filepath))
            if os.path.normcase(fallback) == os.path.normcase(filepath):
                raise
            return self._analyzer.observe(filepath=fallback, context={"source": source})

    def run(self, validated_input: VisionObserveInput) -> ToolResult:
        filepath = resolve_image_path(validated_input.filepath, "vision_observe.png")
        observation = self._observe(filepath, validated_input.source)

        result_data = {
            "description": observation.description,
            "objects_detected": observation.objects_detected,
            "issues": observation.issues,
            "confidence": observation.confidence,
        }

        if observation.is_low_confidence:
            result_data["low_confidence_warning"] = True

        image = describe_image(filepath)
        if image:
            result_data["image"] = {"filepath": filepath, **image}

        return ToolResult.ok(result_data)