"""IterativeBuildSkill"""

import re
from typing import Any, Dict, Optional

from ..base import Skill, SkillResult
from ...agent.self_correct import load_builder_config
from ...tools.capability import Assessment, assess_request


def _library_has(task: str) -> bool:
    """The request names a model of the library ('add a chandelier', 'make a king size bed')."""
    try:
        from ...tools.library_tools import load_library
    except Exception:  # noqa: BLE001
        return False
    text = " " + re.sub(r"[^a-z0-9 ]+", " ", (task or "").lower()) + " "
    for name, spec in load_library().items():
        for alias in [name.replace("_", " ")] + list(spec.get("aliases", [])):
            alias = alias.lower().replace("-", " ")
            if len(alias) >= 3 and f" {alias} " in text:
                return True
    return False


class IterativeBuildSkill(Skill):
    name = "iterative_build"
    description = (
        "For requests our ready tools cannot build well (realistic vehicles, animals, machines, detailed objects, or a reference "
        "image): Gemini writes a build script, it is rendered from 4 angles, reviewed by Gemini vision and improved, without chat turns."
    )

    def __init__(self, tool_caller, config_loader=load_builder_config):
        super().__init__(tool_caller)
        self._load = config_loader

    # "fix this", "this is not a cricket ground", "make it better": a change to what is already there
    _FIX = re.compile(r"\b(?:fix|improve|better|redo|wrong|correct|again|not\s+an?|isn'?t|is\s+not|thik|sahi|"
                      r"theek|galat|sudhar)\b", re.IGNORECASE)

    def _assessment(self, task: str) -> Optional[Assessment]:
        if not task or len(task.split()) > 70:
            return None
        from ...multi_agent.team import _SCENE_WORDS
        if _SCENE_WORDS.search(task) or self._FIX.search(task):
            return None          # whole scenes go to the team planner; fixes edit the scene that is there
        a = assess_request(task)
        if a.verdict == "yes":
            return None
        lowered = task.lower()
        if a.route != "from_image":
            if a.subject and re.search(r"\b(?:the|this|that|my|existing|isko|usko)\s+(?:\w+\s+){0,2}" + re.escape(a.subject) + r"\b", lowered):
                return None
            if re.search(r"\b(?:change|modify|edit|melt|break|broken|twist|bend|paint|recolou?r|resize)\b|\b(?:2|3|4|5|6|7|8|9|10|two|three|four|five|six)\b", lowered):
                return None
        if a.route == "llm":
            return None
        return a

    def can_handle(self, task: str) -> float:
        if _library_has(task):
            return 0.0                    # a ready library model (chandelier, king bed ...) beats writing a script
        a = self._assessment(task)
        if a is None:
            return 0.0
        if not self._load().api_key:
            return 0.0
        if a.route in ("generate_if_no_model", "library_or_downloaded") and self._downloaded_has(a.subject):
            return 0.0
        if a.route == "library_or_downloaded":
            return 0.0                                       # "low poly car": LLM chat stylized banayega
        return 0.94

    def required_permissions(self, tool_registry) -> list:
        return ["build.iterate", "scene.inspect"]

    def execute(self, context: Dict[str, Any]) -> SkillResult:
        from ...agent.models import ToolCall

        task = context.get("task", "")
        a = self._assessment(task) or assess_request(task)
        arguments: Dict[str, Any] = {"request": task}
        if a.image_path:
            arguments["reference_image"] = a.image_path
        if context.get("location"):
            arguments["location"] = context["location"]
        result = self._tool_caller.call(ToolCall(tool_name="build.iterate", arguments=arguments))
        if not result.success:
            return SkillResult.fail(result.error, [])
        data = dict(result.data)
        data["assessment"] = a.as_dict()
        return SkillResult.ok(data=data, steps_completed=[f"build.iterate:{data.get('best_score', 0):g}/10"])

    @staticmethod
    def _downloaded_has(subject: Optional[str]) -> bool:
        if not subject:
            return False
        try:
            from ...tools.local_assets_tools import _singular, load_index, score_entry, search_index
            hits = search_index(load_index(), subject, 1)
            return bool(hits) and score_entry(hits[0], [_singular(subject)]) >= 3.0
        except Exception:  # noqa: BLE001
            return False