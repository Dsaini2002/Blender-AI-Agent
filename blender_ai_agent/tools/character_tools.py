"""
character.create
=================
Hinglish: Cartoon character (poora badan ya sirf chehra/bust) ek call mein. Expression, baal, rang, kapde, chashma/cap sab
parameters se badlte hain. Asli kaam character_builder.py karta hai; yahan input ki safai aur Blender mein rakhna hai.
"""

from dataclasses import dataclass, field
from typing import Any, List, Optional

from .base import Permission, Tool, ToolResult
from .character_builder import (ACCESSORIES, COLORS, EXPRESSIONS, GENDERS, HAIR_STYLES, OUTFITS, QUALITY_CELL, STYLES,
                                build_character_spec, resolve_color)
from .library_tools import place_model
from .models import _coerce_bool, _coerce_number, _vec3, to_plain

_STYLE_WORDS = {"chibi": "chibi", "cute": "chibi", "cartoon": "chibi", "big head": "chibi", "normal": "normal", "tall": "normal",
                "realistic": "normal", "proportional": "normal"}
_GENDER_WORDS = {"boy": "boy", "male": "boy", "man": "boy", "guy": "boy", "ladka": "boy", "girl": "girl", "female": "girl",
                 "woman": "girl", "lady": "girl", "ladki": "girl", "neutral": "neutral", "kid": "neutral", "child": "neutral",
                 "person": "neutral"}
_EXPRESSION_WORDS = {"smile": "happy", "smiling": "happy", "joy": "happy", "joyful": "happy", "cheerful": "happy", "glad": "happy",
                     "laughing": "laugh", "laughter": "laugh", "lol": "laugh", "excited": "laugh", "crying": "sad", "unhappy": "sad",
                     "upset": "sad", "mad": "angry", "furious": "angry", "shocked": "surprised", "surprise": "surprised",
                     "amazed": "surprised", "tired": "sleepy", "sleeping": "sleepy", "bored": "sleepy", "winking": "wink",
                     "calm": "neutral", "serious": "neutral", "normal": "neutral"}
_HAIR_WORDS = {"bald": "none", "no hair": "none", "buzz": "short", "curly": "afro", "ponytail": "ponytail", "pony tail": "ponytail",
               "spikes": "spiky", "punk": "spiky", "bun": "ponytail", "lambe": "long", "chhote": "short"}
_ACCESSORY_WORDS = {"glass": "glasses", "specs": "glasses", "spectacles": "glasses", "chashma": "glasses", "shades": "sunglasses",
                    "hat": "beanie", "topi": "cap", "baseball cap": "cap", "woolly hat": "beanie"}


def _pick(value: Any, allowed, words, label, default=None):
    if value is None or value == "":
        return default
    key = str(value).strip().lower().replace("_", " ")
    if key in allowed:
        return key
    if key in words:
        return words[key]
    raise ValueError(f"CharacterInput.{label} must be one of {list(allowed)}, got '{value}'")


@dataclass
class CharacterInput:
    """
    style       : chibi (bada sir, cute, default) | normal (asli anupaat)
    gender      : boy | girl | neutral   (baal, kapde aur rang ka default isi se)
    skin        : peach, light, fair, tan, brown, dark, olive  (ya koi bhi rang / [r,g,b])
    hair_style  : short | spiky | bob | long | ponytail | afro | none      hair_color: black, brown, blonde, ginger, red, blue, pink...
    eye_color   : brown, blue, green, black, ...
    expression  : happy | laugh | sad | angry | surprised | sleepy | wink | neutral
    outfit      : tshirt (shirt + pants) | dress       shirt_color / pants_color / shoe_color
    accessories : ["glasses"] | ["sunglasses"] | ["cap"] | ["beanie"]   accessory_color
    bust_only   : True = sirf chehra + kandhe (face model)
    height      : poore character ki oonchai metre mein (bust ke liye bhi poore character ke hisaab se)
    """
    name: str = "Character"
    style: str = "chibi"
    gender: str = "neutral"
    skin: Any = "peach"
    hair_style: Optional[str] = None
    hair_color: Any = "brown"
    eye_color: Any = "brown"
    expression: str = "happy"
    outfit: str = "tshirt"
    shirt_color: Any = None
    pants_color: Any = None
    shoe_color: Any = "brown"
    accessories: List[str] = field(default_factory=list)
    accessory_color: Any = "red"
    bust_only: bool = False
    height: float = 1.0
    quality: str = "medium"
    yaw_degrees: float = 0.0
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])

    def __post_init__(self):
        if not self.name or not isinstance(self.name, str):
            raise ValueError("CharacterInput.name must be a non-empty string")
        self.style = _pick(self.style, STYLES, _STYLE_WORDS, "style", "chibi")
        self.gender = _pick(self.gender, GENDERS, _GENDER_WORDS, "gender", "neutral")
        self.expression = _pick(self.expression, EXPRESSIONS, _EXPRESSION_WORDS, "expression", "happy")
        self.outfit = _pick(self.outfit, OUTFITS, {"shirt": "tshirt", "t-shirt": "tshirt", "tee": "tshirt", "skirt": "dress", "frock": "dress"}, "outfit", "tshirt")
        self.hair_style = _pick(self.hair_style, HAIR_STYLES, _HAIR_WORDS, "hair_style", None)
        self.quality = _pick(self.quality, tuple(QUALITY_CELL), {"fast": "low", "draft": "draft", "best": "high", "good": "medium"}, "quality", "medium")

        raw = to_plain(self.accessories)
        if isinstance(raw, str):
            raw = [t for t in raw.replace(",", " ").split() if t]
        cleaned: List[str] = []
        for item in raw or []:
            value = _pick(item, ACCESSORIES, _ACCESSORY_WORDS, "accessories")
            if value not in cleaned:
                cleaned.append(value)
        self.accessories = cleaned

        for attr in ("skin", "hair_color", "eye_color", "shirt_color", "pants_color", "shoe_color", "accessory_color"):
            value = getattr(self, attr)
            if value is not None:
                try:
                    resolve_color(to_plain(value) if not isinstance(value, str) else value)
                except ValueError:
                    from .models import _coerce_color
                    setattr(self, attr, _coerce_color(value, f"CharacterInput.{attr}")[:3])
                else:
                    setattr(self, attr, to_plain(value) if not isinstance(value, str) else value.strip().lower())

        self.bust_only = _coerce_bool(self.bust_only, "CharacterInput.bust_only")
        self.height = _coerce_number(self.height, "CharacterInput.height")
        if not (0.05 <= self.height <= 50):
            raise ValueError("CharacterInput.height must be between 0.05 and 50 metres")
        self.yaw_degrees = _coerce_number(self.yaw_degrees, "CharacterInput.yaw_degrees")
        self.location = _vec3(self.location, "CharacterInput.location")


class CharacterCreateTool(Tool):
    name = "character.create"
    description = (
        "Creates a finished CARTOON CHARACTER (face, eyes, brows, mouth, hair, body, clothes, shoes) in one call, ready to render - "
        "use it for any request like 'cartoon character', 'cute boy/girl', 'chibi', 'mascot', 'make a face / head / bust'. Options: "
        "style chibi (big head, default) | normal; gender boy | girl | neutral; skin (peach, light, fair, tan, brown, dark, olive or any "
        "colour); hair_style short | spiky | bob | long | ponytail | afro | none; hair_color / eye_color / shirt_color / pants_color / "
        "shoe_color (names like blonde, ginger, black, blue, pink, teal... or [r,g,b]); expression happy | laugh | sad | angry | surprised "
        "| sleepy | wink | neutral; outfit tshirt | dress; accessories ['glasses' | 'sunglasses' | 'cap' | 'beanie'] with accessory_color; "
        "bust_only=true for just head + shoulders (a 'face model'); height in metres (1.0 default); location [x,y,z]; yaw_degrees to turn it. "
        "The character faces the camera of Blender's front view. Afterwards you can still change it with mesh.edit (e.g. a bigger head) "
        "or move it with object.transform. To change expression/colour just call character.create again with a new name."
    )
    permission = Permission.SAFE_WRITE
    input_model = CharacterInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: CharacterInput) -> ToolResult:
        spec = build_character_spec({
            "style": v.style, "gender": v.gender, "skin": v.skin, "hair_style": v.hair_style, "hair_color": v.hair_color,
            "eye_color": v.eye_color, "expression": v.expression, "outfit": v.outfit, "shirt_color": v.shirt_color,
            "pants_color": v.pants_color, "shoe_color": v.shoe_color, "accessories": v.accessories,
            "accessory_color": v.accessory_color, "bust_only": v.bust_only, "quality": v.quality,
        })
        # Builder +Y ki taraf dekhta hai; Blender ka front view -Y se dekhta hai => 180 degree ghuma do
        created = place_model(self._bridge, v.name, spec, location=v.location, scale=v.height,
                              yaw_degrees=v.yaw_degrees + 180.0, prefix=f"{v.name}_", colors=None)
        meta = spec["meta"]
        return ToolResult.ok({
            "name": v.name, "object_count": len(created["meshes"]) + len(created["curves"]),
            "meshes": created["meshes"], "curves": created["curves"],
            "root": created["meshes"][0] if created["meshes"] else None, "style": v.style, "gender": v.gender,
            "expression": v.expression, "hair_style": meta["hair_style"], "accessories": v.accessories, "bust_only": v.bust_only,
            "height": v.height, "location": list(v.location),
        })