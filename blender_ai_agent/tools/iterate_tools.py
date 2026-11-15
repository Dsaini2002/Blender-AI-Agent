
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from ..agent.self_correct import BuilderConfig, BuilderError, GeminiClient, SelfCorrectingBuilder, load_builder_config, \
    make_vision_client
from .base import Permission, Tool, ToolResult
from .models import _coerce_number, _vec3


def _report_status(text: str) -> None:
    try:
        from ..copilot.activity import set_text, stop_requested
    except Exception:  # noqa: BLE001
        return
    if stop_requested() and ("writing" in text or "improving" in text):
        raise BuilderError("Stopped by user", "Stopped by user")
    set_text(f"Build loop: {text}")


@dataclass
class BuildIterateInput:
    request: str
    reference_image: Optional[str] = None
    max_iterations: Optional[int] = None
    target_score: Optional[float] = None
    location: Optional[List[float]] = None

    def __post_init__(self):
        if not self.request or not isinstance(self.request, str) or not self.request.strip():
            raise ValueError("BuildIterateInput.request must describe what to build")
        if self.reference_image is not None:
            self.reference_image = str(self.reference_image).strip().strip('"') or None
        if self.max_iterations is not None:
            self.max_iterations = _coerce_number(self.max_iterations, "BuildIterateInput.max_iterations", integer=True)
            if not 1 <= self.max_iterations <= 6:
                raise ValueError("BuildIterateInput.max_iterations must be between 1 and 6")
        if self.target_score is not None:
            self.target_score = _coerce_number(self.target_score, "BuildIterateInput.target_score")
            if not 1 <= self.target_score <= 10:
                raise ValueError("BuildIterateInput.target_score must be between 1 and 10")
        if self.location is not None:
            self.location = _vec3(self.location, "BuildIterateInput.location")


class BuildIterateTool(Tool):
    name = "build.iterate"
    description = (
        "Builds something our ready-made tools cannot make in one call (a car, animal, machine, building, furniture set, anything "
        "complex or specific) by letting Gemini WRITE A BUILD SCRIPT, run it, RENDER the result from 4 angles, LOOK at the renders "
        "(vision) and fix the script - repeating until the review score reaches target_score (default 8/10) or max_iterations "
        "(default 3) is used. The best version stays in the scene. Pass the user's request as `request` (be specific: parts, "
        "colours, size); `reference_image` = a PNG/JPG the result should resemble. Costs 2 Gemini requests per iteration and takes "
        "1-5 minutes. Returns score, what the reviewer still dislikes, the object names and where the script/renders were saved. "
        "Tell the user honestly if the score is below target."
    )
    permission = Permission.SAFE_WRITE
    input_model = BuildIterateInput

    def __init__(self, bridge, caller_getter: Callable[[], Any], registry_getter: Callable[[], Any],
                 llm_factory: Optional[Callable[[BuilderConfig], Any]] = None,
                 config_loader: Callable[[], BuilderConfig] = load_builder_config):
        self._bridge = bridge
        self._caller_getter = caller_getter
        self._registry_getter = registry_getter
        self._llm_factory = llm_factory or (lambda cfg: make_vision_client(cfg))
        self._config_loader = config_loader

    def run(self, v: BuildIterateInput) -> ToolResult:
        cfg = self._config_loader()
        if not cfg.api_key:
            return ToolResult.fail("Gemini API key not found (GEMINI_API_KEY). build.iterate needs Gemini.")
        if v.max_iterations:
            cfg.max_iterations = v.max_iterations
        if v.target_score:
            cfg.target_score = v.target_score
        if v.reference_image and not os.path.isfile(os.path.expanduser(v.reference_image)):
            return ToolResult.fail(f"Reference image not found: {v.reference_image}")
        folder = os.path.join(cfg.output_dir or os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "builds"),
                              time.strftime("%Y%m%d_%H%M%S") + "_" + (re.sub(r"[^A-Za-z0-9]+", "_", v.request)[:30].strip("_") or "build"))
        builder = SelfCorrectingBuilder(self._caller_getter(), self._registry_getter(), self._bridge, self._llm_factory(cfg), cfg,
                                        status=_report_status)
        try:
            report = builder.build(v.request, os.path.expanduser(v.reference_image) if v.reference_image else None, v.location, folder)
        except BuilderError as exc:
            return ToolResult.fail(exc.user_message)
        summary = report.summary()
        if not report.success:
            last = next((i.run_error for i in reversed(report.iterations) if i.run_error), None)
            return ToolResult.fail(f"Build failed: {report.stopped_reason or 'no usable result'}" + (f" (last error: {last})" if last else ""))
        summary["script_file"] = os.path.join(folder, f"iteration_{report.best_iteration}.py") if report.best_iteration else None
        summary["view_images"] = report.images
        summary["note"] = ("Target score reached." if report.reached_target else
                           f"Score {report.best_score:g}/10 (target {cfg.target_score:g}) - tell the user it is not perfect yet; "
                           "build.iterate again or mesh.edit can improve it.")
        return ToolResult.ok(summary)