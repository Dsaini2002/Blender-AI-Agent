"""
LibraryPropSkill
=================
Hinglish: "make a campfire" / "add a lantern" / "aag banao" jaise SHORT requests ko LLM (Gemini)
ke bina, seedha library.place se handle karta hai — zero quota. Sirf tab trigger hota hai jab
request bilkul "<verb> [a/an/the] <model>" jaisi chhoti ho; kuch aur ho (location, count, rang,
"near the table") to LLM wala flow le leta hai taaki request galat na samjhi jaye.

Downloaded GitHub models (download_models.py se) bhi bina Gemini ke: "add a bench from the downloaded models"
-> asset.place_local, best match naam se. "downloaded/local/github models" likhna zaroori hai, warna built-in
library hi use hoti hai (jaise "make a campfire").

Automatic fallback: "add a bottle" jaisa chhota request jiska model built-in library mein nahi hai, par downloaded
models mein ek saaf (poore shabd wala) match hai -> wahi lagata hai. Primitive shabd (cube, sphere...) ya rang/count/jagah
wale requests ko chhodta hai (wo LLM ke paas jaate hain, jo asset policy follow karta hai).

Naya prop kahin khaali jagah par rakhta hai (scene.inspect se dekhta hai ki wahan pehle se kuch
to nahi), taaki do props ek ke upar ek na baith jaayein.
"""

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

# "from the downloaded models", "using local assets", "from github models", "downloaded model se"
_LOCAL_HINT = re.compile(
    r"\s*(?:(?:from|using|use|in|out\s+of|via)\s+)?(?:the\s+|my\s+|all\s+)*"
    r"(?:downloaded|local|github)\s+(?:3d\s+)?(?:models?|assets?|library|files?)(?:\s+se)?\b", re.IGNORECASE)
_ANY_ENGLISH = re.compile(
    rf"^\s*(?:please\s+)?(?:(?:can|could)\s+you\s+)?{_VERBS}\s+(?:me\s+)?(?:(?:a|an|the|one|some)\s+)?"
    r"(?P<alias>[a-z0-9_ ]+?)\s*(?:please|now|here|in\s+the\s+scene)?\s*[.!?]*\s*$"
)
_ANY_HINDI = re.compile(rf"^\s*(?P<alias>[a-z0-9_ ]+?)\s+{_VERBS}\s*[.!?]*\s*$")
# In cheezon ko agent khud primitives se bana leta hai — downloaded model se nahi badalna
_PRIMITIVE_WORDS = {
    "cube", "box", "sphere", "ball", "cone", "cylinder", "torus", "donut", "plane", "ground", "floor", "wall", "walls",
    "camera", "light", "sun", "monkey", "suzanne", "circle", "curve", "spiral", "mesh", "object", "scene", "world",
    "material", "texture", "pyramid", "triangle", "square", "ring", "room", "house", "campsite",
}

# Count / jagah / naam jaisi extra batein hon to ye "sirf ek chhota prop" nahi hai -> LLM wala flow
_NOT_SIMPLE = re.compile(
    r"\b\d+\b|\b(?:two|three|four|five|six|seven|eight|nine|ten|many|several|few|couple|pair|"
    r"at|near|next|beside|behind|above|below|on|with|and|named|called|of)\b")

# Khaali jagah dhoondhne ke candidates (x, y), centre se bahar ki taraf
_SLOTS = [(0, 0), (3, 0), (-3, 0), (0, 3), (0, -3), (3, 3), (-3, 3), (3, -3), (-3, -3),
          (6, 0), (-6, 0), (0, 6), (0, -6), (6, 3), (-6, 3), (6, -3), (-6, -3)]


class LibraryPropSkill(Skill):
    name = "library_props"
    description = (
        "Places a ready-made library model (campfire, torch, lantern, tree, rock, tent, stool, fence, "
        "street lamp, cloud...) from a short request like 'make a campfire' or 'add a lantern'."
    )

    def can_handle(self, task: str) -> float:
        if self._match_local(task):
            return 0.95                      # "from the downloaded models" built-in library se pehle
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
        """Downloaded GitHub models mein se `query` ka best match lagata hai (asset.place_local)."""
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
        """
        "add a bottle" -> 'bottle', agar built-in library mein nahi hai AUR downloaded models mein uske har shabd wala
        saaf naam hai. Warna None (request LLM ke paas jaati hai). Index na ho to bhi None.
        """
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
        if find_model_by_alias(phrase) is not None:
            return None                       # built-in library ka hissa hai (usse 0.9 wala rasta handle karta hai)

        try:
            index = load_index()
        except Exception:  # noqa: BLE001 — index nahi / kharab: chupchaap LLM wale rasta par
            return None
        singular = [_singular(w) for w in words]
        hits = search_index(index, phrase, 1)
        if hits and score_entry(hits[0], singular) >= 3.0 * len(singular):    # har shabd naam mein poora ho
            return phrase
        return None

    @staticmethod
    def _match_local(task: str) -> Optional[str]:
        """'add a bench from the downloaded models' -> 'bench'. Hint na ho / samajh na aaye -> None."""
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
        """scene.inspect se dekho kaun si slot khaali hai. Inspect na chale to origin."""
        from ...agent.models import ToolCall

        result = self._tool_caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        if not result.success or not isinstance(result.data, dict):
            return [0.0, 0.0, 0.0]

        occupied = []
        for obj in result.data.get("objects", []):
            if obj.get("type") not in ("MESH", "CURVE"):
                continue
            scale = obj.get("scale") or [1, 1, 1]
            if max(abs(s) for s in scale) >= 6:   # bada ground plane
                continue
            loc = obj.get("location") or [0, 0, 0]
            occupied.append((loc[0], loc[1]))

        size = (load_library()[model].get("size") if model else None) or [2, 2, 2]
        clearance = max(2.0, max(size[0], size[1]) * 0.8 + 1.0)
        for x, y in _SLOTS:
            if all(math.hypot(x - ox, y - oy) >= clearance for ox, oy in occupied):
                return [float(x), float(y), 0.0]
        return [0.0, 0.0, 0.0]