"""
capability.py
==============
Hinglish: "Kya hamara agent ye bana paayega?" ka faisla — prompt padhkar, bina LLM ke (zero quota).

Verdict:
  yes    hamare tools achhe se bana lenge (library, character, generators, primitives, edits, scene)
  maybe  stylized shayad ban jaye; pehle library / downloaded models, na mile to image->3D
  no     hamare tools se achha nahi banega (asli jaisi gaadi, jaanwar, insaan, machine...) YA user ne khud AI/image se maanga
         -> route: "generate" (prompt -> image -> 3D) ya "from_image" (user ki image -> 3D)

Faisla pehchaan par hai: HARD subjects (vehicles, animals, realistic humans, machines...) + REALISM shabd ("realistic",
"detailed", "asli jaisi") + EXPLICIT AI shabd ("ai se", "from this image", "trellis").
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# ---------------------------------------------------------------- word sets
_HARD = {
    "vehicles": ["car", "cars", "sedan", "suv", "jeep", "truck", "lorry", "bus", "van", "taxi", "ambulance", "limousine", "pickup",
                 "motorcycle", "motorbike", "bike", "bicycle", "scooter", "tractor", "bulldozer", "excavator", "crane", "forklift",
                 "train", "locomotive", "tram", "airplane", "aeroplane", "plane", "jet", "helicopter", "drone", "rocket", "spaceship",
                 "spacecraft", "ship", "boat", "yacht", "submarine", "tank", "gaadi", "kaar", "gadi"],
    "animals": ["dog", "puppy", "cat", "kitten", "horse", "lion", "tiger", "leopard", "elephant", "giraffe", "zebra", "bear", "wolf",
                "fox", "deer", "rabbit", "monkey", "gorilla", "cow", "bull", "sheep", "pig", "goat", "bird", "eagle", "owl", "parrot",
                "duck", "chicken", "fish", "shark", "dolphin", "whale", "turtle", "snake", "lizard", "crocodile", "frog", "spider",
                "butterfly", "bee", "dragon", "dinosaur", "t-rex", "trex", "unicorn", "animal", "kutta", "billi", "ghoda", "sher", "hathi"],
    "people": ["human", "man", "woman", "person", "soldier", "warrior", "knight", "ninja", "pirate", "wizard", "king", "queen",
               "astronaut", "doctor", "police", "athlete", "dancer", "insaan", "aadmi", "aurat"],
    "machines": ["robot", "mech", "android", "cyborg", "gun", "rifle", "pistol", "shotgun", "sword", "katana", "axe", "bow", "shield",
                 "engine", "motor", "turbine", "gearbox", "phone", "smartphone", "laptop", "computer", "keyboard", "camera",
                 "headphones", "watch", "console", "controller", "tv", "television", "speaker", "microphone", "drone"],
    "buildings": ["castle", "cathedral", "church", "temple", "mosque", "palace", "skyscraper", "tower", "stadium", "lighthouse",
                  "windmill", "pyramid", "fort", "mansion", "villa", "factory", "bridge"],
    "objects": ["guitar", "piano", "violin", "drum", "saxophone", "shoe", "sneaker", "boot", "bag", "backpack", "handbag", "jewelry",
                "ring", "necklace", "crown", "statue", "sculpture", "skull", "hand", "hands", "burger", "pizza", "cake", "sushi",
                "flower", "rose", "plant", "cactus", "chandelier", "throne", "helmet", "armor", "armour"],
}
_HARD_WORDS = {w for words in _HARD.values() for w in words}

_BUILDABLE = {
    "primitives": ["cube", "box", "sphere", "ball", "cone", "cylinder", "torus", "donut", "plane", "pyramid", "triangle", "circle",
                   "spiral", "helix", "spring", "tube", "square"],
    "generators": ["bottle", "vase", "glass", "goblet", "cup", "mug", "bowl", "column", "pillar", "pawn", "lamp", "barrel", "candle", "bell",
                   "rock", "stone", "boulder", "snowman", "cloud", "blob", "gear", "cog", "star", "coin", "badge", "tile", "sign", "button",
                   "ground", "terrain", "landscape", "hills", "dunes", "floor"],
    "simple": ["table", "desk", "chair", "bench", "stool", "shelf", "bookshelf", "bed", "sofa", "couch", "wall", "door", "window",
               "stairs", "staircase", "fence", "gate", "house", "hut", "cabin", "room", "tent", "campfire", "bonfire", "fire", "tree",
               "pine", "bush", "mushroom", "lantern", "torch", "campsite", "camp", "kitchen", "garden", "village", "road", "path"],
    "characters": ["character", "characters", "cartoon", "chibi", "mascot", "avatar", "face", "head", "bust", "portrait", "ladka", "ladki"],
    "scene": ["light", "lights", "lighting", "camera", "world", "sky", "render", "material", "texture", "color", "colour", "background"],
}
_BUILDABLE_WORDS = {w for words in _BUILDABLE.values() for w in words}

_REALISM = re.compile(r"\b(?:realistic(?:ally)?|realism|photo[- ]?realistic|lifelike|life[- ]like|hyper[- ]?real\w*|real[- ]looking|looks? real|"
                      r"high[- ]?detail\w*|highly detailed|very detailed|detailed|ultra|4k|8k|hd|cinematic|asli|real jaisi|real jaisa|accurate|authentic)\b")
_SIMPLE = re.compile(r"\b(?:low[- ]?poly|simple|basic|blocky|minecraft|voxel|toy|cartoon|stylized|stylised|cute|chibi|rough|quick|sketch)\b")
_EXPLICIT_AI = re.compile(
    r"\b(?:ai[- ]generated|generate(?:d)? (?:it )?(?:with|using|by) ai|using ai|with ai|ai se|text[- ]to[- ]3d|image[- ]to[- ]3d|img2blender|trellis|"
    r"generative|from (?:an?|this|the|my) (?:image|picture|photo|pic|reference|concept art)|from (?:the )?(?:image|picture|photo) at|"
    r"(?:image|picture|photo) (?:se|ke basis)|photo to 3d|picture to 3d|convert (?:this|the|my) (?:image|picture|photo)|reference image)\b")
_IMAGE_PATH = re.compile(r"""(?:["']([^"']+\.(?:png|jpe?g|webp))["']|((?:[A-Za-z]:[\\/]|~[\\/]|/)[^\s"']+\.(?:png|jpe?g|webp)))""", re.IGNORECASE)
_EDIT = re.compile(r"\b(?:change|modify|edit|move|rotate|scale|resize|delete|remove|rename|duplicate|colou?r it|make it|turn it|badlo|hatao)\b")
_ALIAS_NOISE = {"a", "an", "the", "of", "and", "with", "make", "create", "add", "build", "generate", "design", "give", "me", "please",
                "model", "3d", "object", "some", "my", "banao", "bana", "do"}


@dataclass
class Assessment:
    verdict: str                       # yes | maybe | no
    confidence: float
    route: str                         # build | library_or_downloaded | generate_if_no_model | generate | from_image | llm
    subject: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    realism: bool = False
    simple: bool = False
    explicit_ai: bool = False
    image_path: Optional[str] = None
    hard_category: Optional[str] = None

    def as_dict(self) -> Dict:
        return {"verdict": self.verdict, "confidence": round(self.confidence, 2), "route": self.route, "subject": self.subject,
                "reasons": list(self.reasons), "realism": self.realism, "simple": self.simple, "explicit_ai": self.explicit_ai,
                "image_path": self.image_path, "hard_category": self.hard_category}


def _words(text: str) -> List[str]:
    return re.findall(r"[a-z][a-z\-']*", text.lower())


def _library_words() -> set:
    try:
        from .library_tools import load_library
        names = set()
        for key, spec in load_library().items():
            names.update(key.replace("_", " ").split())
            for alias in spec.get("aliases", []):
                names.update(str(alias).lower().split())
        return {n for n in names if n not in _ALIAS_NOISE}
    except Exception:  # noqa: BLE001
        return set()


def assess_request(text: str) -> Assessment:
    """Prompt ko padhkar Assessment deta hai. Kabhi exception nahi."""
    raw = (text or "").strip()
    lowered = raw.lower()
    words = _words(lowered)
    wordset = set(words)

    image_match = _IMAGE_PATH.search(raw)
    image_path = (image_match.group(1) or image_match.group(2)) if image_match else None
    realism = bool(_REALISM.search(lowered))
    simple = bool(_SIMPLE.search(lowered))
    explicit = bool(_EXPLICIT_AI.search(lowered)) or image_path is not None
    hard = [w for w in words if w in _HARD_WORDS]
    hard_category = next((cat for cat, ws in _HARD.items() if hard and hard[0] in ws), None)
    buildable = [w for w in words if w in _BUILDABLE_WORDS] or [w for w in words if w in _library_words()]
    subject = hard[0] if hard else (buildable[0] if buildable else None)

    base = dict(subject=subject, realism=realism, simple=simple, explicit_ai=explicit, image_path=image_path, hard_category=hard_category)

    if explicit:
        route = "from_image" if image_path or re.search(r"\b(?:this|the|my|an?) (?:image|picture|photo|pic)\b|image at", lowered) and image_path else "generate"
        if image_path:
            route = "from_image"
        return Assessment("no", 1.0, route, reasons=["Aapne khud AI / image se banane ko kaha" + (f" (image: {image_path})" if image_path else "")], **base)

    # character / face: hamara khud ka best tool hai (hard subject 'human'/'man' hone par bhi)
    if wordset & set(_BUILDABLE["characters"]) and not (realism and wordset & {"human", "person", "man", "woman"}):
        return Assessment("yes", 0.95, "build", reasons=["Cartoon character / face: character.create ka kaam"], **base)

    if hard:
        if realism and not simple:
            return Assessment("no", 0.92, "generate", reasons=[f"'{hard[0]}' ({hard_category}) asli jaisa banana hamare tools se achha nahi hota; "
                                                              "prompt -> image -> 3D behtar rahega"], **base)
        if simple:
            return Assessment("maybe", 0.6, "library_or_downloaded", reasons=[f"Stylized/low-poly '{hard[0]}': library / downloaded model ya "
                                                                             "primitives se banane ki koshish theek hai"], **base)
        return Assessment("maybe", 0.7, "generate_if_no_model", reasons=[f"'{hard[0]}' ({hard_category}) mushkil subject hai: pehle downloaded "
                                                                       "models dekho, na mile to prompt -> image -> 3D"], **base)

    if buildable or _EDIT.search(lowered):
        return Assessment("yes", 0.9, "build", reasons=["Ye hamare tools (library / generators / primitives / edit) se ban jaata hai"], **base)

    return Assessment("maybe", 0.5, "llm", reasons=["Subject pehchaana nahi gaya: LLM koshish karega; na bane to image -> 3D"], **base)


def image_prompt_for(subject_prompt: str, style: str = "auto") -> str:
    """TRELLIS ko saaf, akeli cheez ki image chahiye: safed background, beech mein, 3/4 view, bina parchhai."""
    core = " ".join((subject_prompt or "").split())
    core = re.sub(r"^(?:please\s+)?(?:(?:can|could|would) you\s+)?(?:make|create|generate|build|design|draw|add|give|banao|bana do)\s+(?:me\s+)?"
                  r"(?:(?:a|an|the|some|one)\s+)?", "", core, flags=re.IGNORECASE)
    core = re.sub(r"\s*(?:,|\.)?\s*(?:using|with|by)\s+(?:ai|trellis)\b.*$", "", core, flags=re.IGNORECASE)
    core = re.sub(r"\b(?:as a )?3d model\b", "", core, flags=re.IGNORECASE)
    core = " ".join(core.split()).strip(" ,.") or (subject_prompt or "object").strip()
    style_text = {"auto": "highly detailed, realistic materials", "realistic": "photorealistic, highly detailed, realistic materials",
                  "stylized": "stylized 3D render, clean shapes, vibrant colours", "lowpoly": "low-poly stylized, flat colours"}.get(style, style)
    return (f"A single {core}, the whole object fully visible and centered, three-quarter front view, plain pure white background, "
            f"soft even studio lighting, no cast shadow, no text, no watermark, {style_text}, 3D asset reference render")