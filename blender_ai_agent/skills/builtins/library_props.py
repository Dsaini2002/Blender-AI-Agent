"""LibraryPropSkill"""

import math
import re
from typing import Any, Dict, List, Optional

from ..base import Skill, SkillResult
from ...tools.library_tools import find_model_by_alias, load_library
from ...tools.local_assets_tools import _singular, _words, load_index, score_entry, search_index

_VERBS = r"(?:make|create|add|place|build|spawn|put|generate|banao|bana\s+do|lagao|lagado)"
_ENGLISH = re.compile(
    rf"^\s*(?:please\s+)?(?:(?:can|could)\s+you\s+)?{_VERBS}\s+(?:me\s+)?(?:(?:a|an|the|one|some)\s+)?"
    r"(?P<alias>[a-z ]+?)\s*(?:please|now|here|in\s+the\s+scene)?\s*[.!?]*\s*$"
)
_HINDI = re.compile(rf"^\s*(?P<alias>[a-z ]+?)\s+{_VERBS}\s*[.!?]*\s*$")

_LOCAL_HINT = re.compile(
    r"\s*(?:(?:from|using|use|in|out\s+of|via)\s+)?(?:the\s+|my\s+|all\s+)*"
    r"(?:downloaded|local|github)\s+(?:3d\s+)?(?:models?|assets?|library|files?)(?:\s+se)?\b", re.IGNORECASE)
_ANY_ENGLISH = re.compile(
    rf"^\s*(?:please\s+)?(?:(?:can|could)\s+you\s+)?{_VERBS}\s+(?:me\s+)?(?:(?:a|an|the|one|some)\s+)?"
    r"(?P<alias>[a-z0-9_ ]+?)\s*(?:please|now|here|in\s+the\s+scene)?\s*[.!?]*\s*$"
)
_ANY_HINDI = re.compile(rf"^\s*(?P<alias>[a-z0-9_ ]+?)\s+{_VERBS}\s*[.!?]*\s*$")
_PRIMITIVE_WORDS = {
    "cube", "box", "sphere", "ball", "cone", "cylinder", "torus", "donut", "plane", "ground", "floor", "wall", "walls",
    "camera", "light", "sun", "monkey", "suzanne", "circle", "curve", "spiral", "mesh", "object", "scene", "world",
    "material", "texture", "pyramid", "triangle", "square", "ring", "room", "house", "campsite",
}

# Broad subjects: a single downloaded part ("BuildingBase") is never what the user means. Let the agent plan these.
_BROAD_SUBJECTS = {
    "building", "skyscraper", "city", "town", "village", "street", "road", "school", "college", "university",
    "campus", "office", "hospital", "castle", "palace", "temple", "church", "bridge", "park", "garden", "landscape",
    "environment", "vehicle", "car", "truck", "bus", "train", "plane", "aircraft", "ship", "boat", "robot",
    "character", "person", "human", "man", "woman", "people", "animal", "creature", "monster", "furniture",
    "interior", "kitchen", "bedroom", "bathroom", "living", "level", "map", "world",
}

_NOT_SIMPLE = re.compile(
    r"\b\d+\b|\b(?:two|three|four|five|six|seven|eight|nine|ten|many|several|few|couple|pair|"
    r"at|near|next|beside|behind|above|below|on|with|and|named|called|of)\b")

_SLOTS = [(0, 0), (3, 0), (-3, 0), (0, 3), (0, -3), (3, 3), (-3, 3), (3, -3), (-3, -3),
          (6, 0), (-6, 0), (0, 6), (0, -6), (6, 3), (-6, 3), (6, -3), (-6, -3)]


_PART_WORDS = {
    "base", "part", "piece", "fragment", "segment", "section", "module", "corner", "edge", "trim", "tile", "panel",
    "wall", "roof", "floor", "door", "window", "frame", "foundation", "platform", "top", "bottom", "side", "half",
    "leg", "arm", "head", "hand", "foot", "handle", "lid", "cap", "wheel", "stand", "socket", "mount", "debris",
    "broken", "collider", "lod", "proxy", "placeholder",
}


def _same_object(entry: Dict[str, Any], query_words: List[str]) -> bool:
    """Reject an asset that is only a part of what was asked for ('BuildingBase', 'Car_Wheel', 'Table_Leg'):
    a part word in the asset's name must also be in the request."""
    name_words = {_singular(w) for w in _words(entry.get("name", "")) if not w.isdigit()}
    return not any(w in _PART_WORDS and w not in query_words for w in name_words)


class LibraryPropSkill(Skill):
    name = "library_props"
    description = (
        "Places a ready-made library model (campfire, torch, lantern, tree, rock, tent, stool, fence, "
        "street lamp, cloud...) from a short request like 'make a campfire' or 'add a lantern'."
    )

    def can_handle(self, task: str) -> float:
        if self._match_local(task):
            return 0.95
        if self._match(task):
            return 0.9
        return 0.85 if self._match_fallback(task) else 0.0

    def required_permissions(self, tool_registry) -> list:
        return ["library.place", "asset.place_local", "scene.inspect"]

    def execute(self, context: Dict[str, Any]) -> SkillResult:
        task = context.get("task", "")
        query = self._match_local(task)
        if query:
            return self._place_downloaded(query, context)

        model = self._match(task)
        if model is None:
            fallback = self._match_fallback(task)
            if fallback:
                return self._place_downloaded(fallback, context)
            return SkillResult.fail("No library model recognised in the request.", [])

        location = context.get("location") or self._free_spot(model)

        from ...agent.models import ToolCall
        result = self._tool_caller.call(ToolCall(tool_name="library.place", arguments={
            "model": model, "location": list(location)}))
        if not result.success:
            return SkillResult.fail(f"library.place failed: {result.error}", [])

        return SkillResult.ok(data=result.data, steps_completed=[f"library.place:{model}"])

    # ------------------------------------------------------------------
    def _place_downloaded(self, query: str, context: Dict[str, Any]) -> SkillResult:
        from ...agent.models import ToolCall

        location = context.get("location") or self._free_spot(None)
        result = self._tool_caller.call(ToolCall(tool_name="asset.place_local", arguments={
            "query": query, "location": list(location)}))
        if not result.success:
            return SkillResult.fail(f"Downloaded models: {result.error}", [])

        data = dict(result.data)
        data["source"] = "downloaded"
        return SkillResult.ok(data=data, steps_completed=[f"asset.place_local:{data.get('name', query)}"])

    @staticmethod
    def _match_fallback(task: str) -> Optional[str]:
        text = (task or "").lower().strip()
        if not text or _LOCAL_HINT.search(text):
            return None
        phrase = None
        for pattern in (_ANY_ENGLISH, _ANY_HINDI):
            found = pattern.match(text)
            if found:
                phrase = found.group("alias").strip()
                break
        if not phrase or _NOT_SIMPLE.search(phrase):
            return None
        words = _words(phrase) or phrase.split()
        if not words or len(words) > 3 or any(w in _PRIMITIVE_WORDS for w in words):
            return None
        if any(_singular(w) in _BROAD_SUBJECTS for w in words):
            return None
        if find_model_by_alias(phrase) is not None:
            return None

        try:
            index = load_index()
        except Exception:  # noqa: BLE001 
            return None
        singular = [_singular(w) for w in words]
        hits = search_index(index, phrase, 1)
        if hits and score_entry(hits[0], singular) >= 3.0 * len(singular) and _same_object(hits[0], singular):
            return phrase
        return None

    @staticmethod
    def _match_local(task: str) -> Optional[str]:
        text = (task or "").lower().strip()
        if not _LOCAL_HINT.search(text):
            return None
        cleaned = _LOCAL_HINT.sub(" ", text)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,!?")
        for pattern in (_ANY_ENGLISH, _ANY_HINDI):
            found = pattern.match(cleaned)
            if found:
                phrase = found.group("alias").strip()
                if phrase and not _NOT_SIMPLE.search(phrase):
                    return phrase
        return None

    @staticmethod
    def _match(task: str) -> Optional[str]:
        text = (task or "").lower().strip()
        for pattern in (_ENGLISH, _HINDI):
            found = pattern.match(text)
            if found:
                model = find_model_by_alias(found.group("alias"))
                if model:
                    return model
        return None

    def _free_spot(self, model: Optional[str]) -> List[float]:
        from ...agent.models import ToolCall

        result = self._tool_caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        if not result.success or not isinstance(result.data, dict):
            return [0.0, 0.0, 0.0]

        occupied = []
        for obj in result.data.get("objects", []):
            if obj.get("type") not in ("MESH", "CURVE"):
                continue
            scale = obj.get("scale") or [1, 1, 1]
            if max(abs(s) for s in scale) >= 6:
                continue
            loc = obj.get("location") or [0, 0, 0]
            occupied.append((loc[0], loc[1]))

        size = (load_library()[model].get("size") if model else None) or [2, 2, 2]
        clearance = max(2.0, max(size[0], size[1]) * 0.8 + 1.0)
        for x, y in _SLOTS:
            if all(math.hypot(x - ox, y - oy) >= clearance for ox, oy in occupied):
                return [float(x), float(y), 0.0]
        return [0.0, 0.0, 0.0]