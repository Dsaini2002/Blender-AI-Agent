"""
CartoonCharacterSkill
======================
Hinglish: "make a cartoon character", "cute girl with long blonde hair and glasses, laughing", "angry boy with spiky red hair",
"cartoon face", "ladka character banao" jaise requests ko LLM (Gemini) ke bina seedha character.create se banata hai — zero quota.
Text se ye cheezein khud nikalta hai: ladka/ladki, expression, baal ka style aur rang, aankh/skin/shirt/pants/shoes ka rang, dress,
chashma/cap/hat, "face/head/bust" (sirf chehra), "named X". Jo samajh na aaye uska default (peach skin, brown baal, happy).

Ye sirf NAYA character banane ke liye hai. "Character ke baal laal karo" jaise badlav, animation (walk/dance/rig), ya kai characters
(3 characters) wale requests LLM ke paas jaate hain (wo character.create / mesh.edit khud chalata hai).
"""

import math
import re
from typing import Any, Dict, List, Optional

from ..base import Skill, SkillResult
from ...tools.character_builder import COLORS
from .library_props import _SLOTS

_CREATE = r"(?:make|create|add|build|generate|design|draw|give|need|want|get|banao|bana|chahiye|do|dikhao)"
_NOUN = (r"(?:character|characters|mascot|avatar|toon|cartoon|chibi|person|kid|child|boy|girl|man|woman|guy|lady|ladka|ladki|"
         r"face|head|bust|portrait|headshot|chehra)")
_TRIGGER = re.compile(rf"\b{_CREATE}\b.*\b{_NOUN}\b|\b(?:cartoon|chibi|toon|mascot|cute|anime)\b.*\b{_NOUN}\b|\b{_NOUN}\b.*\b(?:banao|bana do|chahiye)\b")
_NEEDS_CARTOON_OR_CHARACTER = re.compile(r"\b(?:cartoon|chibi|toon|mascot|character|avatar|face|head|bust|portrait|headshot|chehra|cute|anime)\b")
_NOT_SIMPLE = re.compile(
    r"\b(?:animate|animation|walk|walking|run|running|dance|dancing|rig|rigged|pose|posed|jump|wave|waving|sit|sitting|hold|holding|"
    r"next to|beside|near|behind|in front|on top|inside|with a (?:car|dog|cat|house|tree|sword|gun|ball)|"
    r"two|three|four|five|six|seven|eight|nine|ten|\d+)\b")
_EDIT = re.compile(r"\b(?:the|this|that|my|existing)\s+(?:cartoon\s+)?(?:character|boy|girl|face|head|mascot|avatar)\b|\b(?:change|modify|edit|make it|turn it|badlo)\b")

_EXPRESSIONS = [
    ("laugh", r"laugh\w*|lol|excited|haha"), ("wink", r"wink\w*"), ("surprised", r"surpris\w*|shock\w*|amaz\w*|wow"),
    ("angry", r"angry|mad|furious|annoyed|gussa"), ("sad", r"sad|cry\w*|unhappy|upset|dukhi"), ("sleepy", r"sleep\w*|tired|bored|neend"),
    ("happy", r"happy|smil\w*|joy\w*|cheerful|glad|khush"), ("neutral", r"neutral|serious|calm|straight face"),
]
_HAIR_STYLES = [("none", r"bald|no hair|ganja"), ("spiky", r"spik\w+|punk"), ("ponytail", r"pony\s?tail|bun"), ("afro", r"afro|curly"),
                ("bob", r"bob"), ("long", r"long(?:\s+\w+)?\s+hair|long[- ]haired|lambe"), ("short", r"short(?:\s+\w+)?\s+hair|short[- ]haired|buzz|chhote")]
_COLOR_WORD = "|".join(sorted(COLORS, key=len, reverse=True))


def _color_before(text: str, nouns: str) -> Optional[str]:
    m = re.search(rf"\b({_COLOR_WORD})\s+(?:colou?red\s+)?(?:{nouns})\b", text)
    return m.group(1) if m else None


def parse_character_request(text: str) -> Dict[str, Any]:
    """Text -> character.create ke arguments (sirf wahi jo text mein mile)."""
    t = " ".join((text or "").lower().replace(",", " , ").replace(".", " ").split())
    args: Dict[str, Any] = {}

    if re.search(r"\b(?:girl|woman|lady|female|ladki|she|queen|princess)\b", t):
        args["gender"] = "girl"
    elif re.search(r"\b(?:boy|man|guy|male|ladka|he|king|prince)\b", t):
        args["gender"] = "boy"
    if re.search(r"\b(?:realistic proportions?|normal proportions?|proportional|tall|adult|full[- ]size)\b", t):
        args["style"] = "normal"
    if re.search(r"\b(?:face|head|bust|portrait|headshot|chehra)\b", t) and not re.search(r"full[- ]body|whole body|poora|with body", t):
        args["bust_only"] = True

    for name, pattern in _EXPRESSIONS:
        if re.search(rf"\b(?:{pattern})\b", t):
            args["expression"] = name
            break
    for name, pattern in _HAIR_STYLES:
        if re.search(rf"\b(?:{pattern})\b", t):
            args["hair_style"] = name
            break

    hair = _color_before(t, "hair|haired|hairs|baal")
    if hair:
        args["hair_color"] = hair
    eyes = _color_before(t, "eyes|eyed|aankhen|aankhon")
    if eyes:
        args["eye_color"] = eyes
    skin = _color_before(t, "skin|complexion")
    if skin:
        args["skin"] = skin
    if re.search(r"\b(?:dress|frock|skirt|gown)\b", t):
        args["outfit"] = "dress"
    shirt = _color_before(t, "shirt|t-shirt|tshirt|top|hoodie|jacket|sweater|dress|frock|skirt|gown|kurta")
    if shirt:
        args["shirt_color"] = shirt
    pants = _color_before(t, "pants|jeans|trousers|shorts|pant")
    if pants:
        args["pants_color"] = pants
    shoes = _color_before(t, "shoes|boots|sneakers|shoe")
    if shoes:
        args["shoe_color"] = shoes

    accessories: List[str] = []
    if re.search(r"\b(?:sunglasses|shades)\b", t):
        accessories.append("sunglasses")
    elif re.search(r"\b(?:glasses|spectacles|specs|chashma|eyeglasses)\b", t):
        accessories.append("glasses")
    if re.search(r"\b(?:cap|topi)\b", t):
        accessories.append("cap")
    elif re.search(r"\b(?:hat|beanie|woolly)\b", t):
        accessories.append("beanie")
    if accessories:
        args["accessories"] = accessories
        accessory_color = _color_before(t, "cap|hat|beanie|topi")
        if accessory_color:
            args["accessory_color"] = accessory_color

    if re.search(r"\bdraft\b", t):
        args["quality"] = "draft"
    elif re.search(r"\b(?:quick|fast|low[- ]poly|jaldi)\b", t):
        args["quality"] = "low"
    elif re.search(r"\b(?:high quality|best quality|detailed|hd|smooth)\b", t):
        args["quality"] = "high"

    named = re.search(r"\b(?:named|called|naam)\s+([a-z][a-z0-9_]{0,20})", t)
    if named:
        args["name"] = named.group(1).capitalize()
    return args


class CartoonCharacterSkill(Skill):
    name = "cartoon_character"
    description = (
        "Builds a finished cartoon character or face (head, eyes, brows, mouth, hair, body, clothes) from a short description, "
        "without the LLM. Understands boy/girl, expression, hair style+colour, eye/skin/shirt/pants colours, dress, glasses/cap/hat, "
        "'face/head/bust only' and 'named X'."
    )

    def can_handle(self, task: str) -> float:
        text = (task or "").lower()
        if not _TRIGGER.search(text) or not _NEEDS_CARTOON_OR_CHARACTER.search(text):
            return 0.0
        if _NOT_SIMPLE.search(text) or _EDIT.search(text) or len(text.split()) > 40:
            return 0.0
        return 0.97

    def required_permissions(self, tool_registry) -> list:
        return ["character.create", "scene.inspect"]

    def execute(self, context: Dict[str, Any]) -> SkillResult:
        from ...agent.models import ToolCall

        task = context.get("task", "")
        args = parse_character_request(task)
        occupied, taken_names = self._scene(ToolCall)
        base = args.get("name", "Character")
        args["name"] = self._unique_name(base, taken_names)
        args["location"] = context.get("location") or self._free_spot(occupied)

        result = self._tool_caller.call(ToolCall(tool_name="character.create", arguments=args))
        if not result.success:
            return SkillResult.fail(f"Character could not be created: {result.error}", [])
        data = dict(result.data)
        data["interpreted_as"] = {k: v for k, v in args.items() if k not in ("location",)}
        return SkillResult.ok(data=data, steps_completed=[f"character.create:{args['name']}"])

    # ------------------------------------------------------------------
    def _scene(self, ToolCall):
        result = self._tool_caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        if not result.success or not isinstance(result.data, dict):
            return [], set()
        occupied, names = [], set()
        for obj in result.data.get("objects", []):
            names.add(obj.get("name", ""))
            if obj.get("type") not in ("MESH", "CURVE"):
                continue
            if max(abs(s) for s in (obj.get("scale") or [1, 1, 1])) >= 6:
                continue
            loc = obj.get("location") or [0, 0, 0]
            occupied.append((loc[0], loc[1]))
        return occupied, names

    @staticmethod
    def _unique_name(base: str, names) -> str:
        if not any(n.startswith(f"{base}_") for n in names):
            return base
        for k in range(2, 100):
            if not any(n.startswith(f"{base}{k}_") for n in names):
                return f"{base}{k}"
        return base

    @staticmethod
    def _free_spot(occupied) -> List[float]:
        for x, y in _SLOTS:
            if all(math.hypot(x - ox, y - oy) >= 1.8 for ox, oy in occupied):
                return [float(x), float(y), 0.0]
        return [0.0, 0.0, 0.0]