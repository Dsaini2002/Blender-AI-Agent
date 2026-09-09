"""
VisionObserveTool — Step 5.5
================================
Hinglish: Poore vision pipeline ko Phase 2 ke Tool interface mein
wrap karta hai — taaki Agent isko exactly waise hi call kare jaise
object.create ya scene.inspect: `tool.execute({...})`.

Architecture rule maintain hoti hai: Agent ko VisionAnalyzer, Capture,
ya VisionProvider ka pata nahi — sirf "vision.observe" tool naam pata hai.
"""

from dataclasses import dataclass

from ..tools.base import Permission, Tool, ToolResult


@dataclass
class VisionObserveInput:
    """vision.observe tool ke liye input contract."""
    source: str = "render"
    filepath: str = "/tmp/vision_observe.png"

    def __post_init__(self):
        valid_sources = ("viewport", "render", "camera")
        if self.source not in valid_sources:
            raise ValueError(f"VisionObserveInput.source must be one of {valid_sources}, got '{self.source}'")
        if not self.filepath:
            raise ValueError("VisionObserveInput.filepath must be a non-empty string")


class VisionObserveTool(Tool):
    name = "vision.observe"
    description = "Captures the current scene visually and returns a structured observation."
    permission = Permission.READ_ONLY
    input_model = VisionObserveInput

    def __init__(self, analyzer):
        self._analyzer = analyzer

    def run(self, validated_input: VisionObserveInput) -> ToolResult:
        observation = self._analyzer.observe(
            filepath=validated_input.filepath,
            context={"source": validated_input.source},
        )

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

        return ToolResult.ok(result_data)