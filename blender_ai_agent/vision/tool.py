"""
VisionObserveTool — Step 5.5
================================
Hinglish: Poore vision pipeline ko Phase 2 ke Tool interface mein
wrap karta hai — taaki Agent isko exactly waise hi call kare jaise
object.create ya scene.inspect: `tool.execute({...})`.

Architecture rule maintain hoti hai: Agent ko VisionAnalyzer, Capture,
ya VisionProvider ka pata nahi — sirf "vision.observe" tool naam pata hai.

Advanced: filepath ab render.preview jaise hi resolve hota hai (image_paths.resolve_image_path), isliye
"render ne ek jagah save kiya, vision ne doosri jagah dhoondha" wala Errno 2 nahi aata. Phir bhi file na mile
to ek baar Temp folder mein dobara koshish hoti hai.
"""

import os
import tempfile
from dataclasses import dataclass, field

from ..image_paths import describe_image, resolve_image_path
from ..tools.base import Permission, Tool, ToolResult


def _default_vision_filepath() -> str:
    # Hinglish: "/tmp/..." sirf Linux/Mac par kaam karta hai - Windows
    # (jahan sabse zyada users hain) par ye path exist hi nahi karta,
    # isliye vision.observe crash ho jaata tha jab model filepath khud
    # nahi bhejta tha. tempfile.gettempdir() har OS par sahi temp
    # folder deta hai (Windows: AppData\Local\Temp, jaisa render.preview
    # khud bhi use karta hai).
    return os.path.join(tempfile.gettempdir(), "vision_observe.png")


@dataclass
class VisionObserveInput:
    """vision.observe tool ke liye input contract."""
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
            # Hinglish: aakhri suraksha — file kahin aur ban gayi ho to Temp folder mein ek baar aur try karo.
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
            # Hinglish: Tool FAIL nahi karta — data wahi return hota hai,
            # lekin "low_confidence" flag add ho jaata hai. Caller
            # (Agent/RepairableExecutionLoop) decide karega destructive
            # action lena hai ya nahi — Step 5.17 human-in-the-loop
            # philosophy ke hisaab se.
            result_data["low_confidence_warning"] = True

        # Saboot: jis image ko dekha gaya wo asal mein disk par hai (sirf tab jodte hain jab file ho).
        image = describe_image(filepath)
        if image:
            result_data["image"] = {"filepath": filepath, **image}

        return ToolResult.ok(result_data)