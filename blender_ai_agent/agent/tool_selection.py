"""Send the model only the tools a request can need.

Every tool schema costs prompt tokens on every turn, and a long tool list makes weaker models pick the wrong tool.
Core tools are always sent; specialist tools are added when the request mentions their subject, or when the model
already used them earlier in the same run.
"""

import re
from typing import Iterable, List, Optional, Sequence

OPTIONAL_TOOLS = {
    "retopology.analyze": r"retopo|remesh|topolog|quad|poly ?count|polygons?|decimat|low[- ]?poly|clean ?mesh|faces",
    "retopology.remesh": r"retopo|remesh|topolog|quad|poly ?count|polygons?|decimat|low[- ]?poly|clean ?mesh|faces",
    "asset.import_model": r"import|\.obj\b|\.fbx\b|\.glb\b|\.gltf\b|\.stl\b|file|path|folder",
    "asset.list_blend_objects": r"\.blend\b|blend file|append|link",
    "asset.import_blend": r"\.blend\b|blend file|append|link",
    "template.build": r"human|person|man\b|woman|people|robot|superhero|humanoid|body|skeleton|spider",
    "python.execute": r"python|script|bmesh|blenderkit|extrude|loop ?cut|inset|knife|vertex|vertices|edge loop|code",
    "material.nodes": r"node|shader|procedural|custom material|texture|noise|gradient|mix shader",
    "mesh.script": r"formula|function|math|equation|per[- ]vertex|custom (shape|deform)",
    "mesh.damage": r"broken|break|crack|chip|dent|damage|worn|old|rust|scratch|shatter",
    "mesh.grandstand": r"stadium|stands?\b|grandstand|bleacher|seating|tribune|arena|court|ground|field|pitch|"
                       r"audience|spectator|gallery|amphitheat|auditorium|stage",
    "mesh.field_markings": r"stadium|pitch|field|court|ground|football|soccer|tennis|cricket|badminton|volley|"
                           r"basketball|marking|lines|sports? hall|arena",
    "mesh.building": r"building|hostel|hotel|college|school|office|apartment|flat\b|hospital|campus|block|stor(e)?y|"
                     r"storeys|floors|\bG ?\+ ?\d|dorm|residen|tower|mall|institute|university|facade|balcon",
    "mesh.boundary_wall": r"boundary|compound|gate|security|campus|enclos|perimeter|wall around|walls around|fence",
    "text.create": r"sign|text|letter|name ?board|label|logo|title|written|reading|banner|board|plaque|\"",
}

# output the user may ask for in any language ('file bana do', 'save kar do', '.blend') - never hidden
ALWAYS = {"scene.save", "scene.organize"}
SAVE_INTENT = re.compile(r"\bsave|\.blend\b|\bfile\s+(bana|banao|bana\s*do|me|mein|main)|\bsave\s*kar|sahej|"
                         r"\bstore\s+(it|the\s+scene)|\bexport\b", re.IGNORECASE)


def wants_save(text: str) -> bool:
    return bool(SAVE_INTENT.search(text or ""))


def _text_matches(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE) is not None


def select_tools(definitions: Sequence, request_text: str = "", used: Optional[Iterable[str]] = None) -> List:
    """Keep every core tool, plus optional tools whose subject appears in `request_text` or that were `used`."""
    used = set(used or ())
    text = request_text or ""
    chosen = []
    for definition in definitions:
        pattern = OPTIONAL_TOOLS.get(definition.name)
        if definition.name in ALWAYS or pattern is None or definition.name in used or _text_matches(pattern, text):
            chosen.append(definition)
    return chosen
