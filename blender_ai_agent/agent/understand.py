"""The AI reads the request FIRST - before anything is built.

One small call to the AI picked in the panel turns the request (English, Hindi, Hinglish ...) into:
  kind       new scene / edit of what exists / only a question
  checklist  every thing asked for, exact counts, the position the user gave ("" = the placement step decides)
  tools      the tools the builder needs (only those are sent with every step -> much smaller requests)
  missing    parts no tool makes -> how the builder makes them itself (python.execute, mesh.create, build.iterate ...)
  save       does the user want a .blend file, and its name

When the AI cannot answer (no key, bad JSON, an error), the old rules do it (checklist.make_checklist,
tool_selection.select_tools) - nothing breaks.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .checklist import Item, SYNONYMS, builder_hint, checklist_text, is_edit, make_checklist

# always sent, whatever the AI picked: inspecting, the basic build / move / measure / colour tools, saving
CORE_TOOLS = {
    "scene.inspect", "object.create", "object.delete", "object.transform", "object.measure", "object.move_by",
    "object.place_on", "object.place_next_to", "object.snap_to_ground", "object.rename", "object.duplicate",
    "material.recipe", "material.create", "material.assign", "object.recolor", "light.create", "camera.create",
    "library.place", "library.list", "scene.save", "scene.organize",
}
# what the builder uses to MAKE a tool that does not exist
MAKER_TOOLS = {"python.execute", "mesh.create", "mesh.script", "mesh.lathe", "mesh.sdf", "build.iterate", "mesh.edit"}

UNDERSTAND_PROMPT = """You are the planner of a Blender AI copilot. Read the user's request (it may be English, Hindi or
Hinglish) BEFORE anything is built and answer with ONE JSON object only:
{
  "kind": "new" | "edit" | "question",
  "summary": "one short line: what will be built or changed",
  "checklist": [{"item": "book", "count": 2, "position": "on the table", "size": "0.24 x 0.17 x 0.03 m"}],
  "tools": ["object.create", "..."],
  "missing": [{"what": "laptop hinge", "how": "mesh.create"}],
  "save": {"wanted": false, "filename": ""}
}
Rules:
- checklist: EVERY separate thing the request asks for, with the exact count ("two books" = 2, "books" without a
  number = 3). Use short English names (table, book, laptop, lamp). position = only what the user said about where it
  goes ("on the table", "left of the sofa", "at (2, 3, 0)", "in the corner"); "" when the user said nothing - a later
  step decides the best place. Things that come WITH something ("a table with two books") go on it ("on the table").
  Do not add things the user did not ask for.
- size: a real-world size (metres) for each item, unless the user gave one - then the user's.
- tools: every tool name from the list below the builder will need (be generous, 10-25 names).
- missing: parts that no tool below makes well; "how" = the maker tool the builder uses to make it itself:
  python.execute (writes Blender Python), mesh.create (raw vertices/faces), mesh.script (a formula per vertex),
  mesh.lathe / mesh.sdf (round / organic), build.iterate (a whole complex model written as a script and reviewed).
- save.wanted = true when the user wants a file ("save", ".blend", "file bana do", "export"); filename from the
  request, else a short name ending in .blend.
- kind: "edit" = a change to objects that already exist (colour, move, resize, delete, replace); "question" = the user
  only asks something; else "new".
TOOLS (name - what it does):
"""


@dataclass
class Understanding:
    kind: str = "new"
    summary: str = ""
    checklist: List[Item] = field(default_factory=list)
    tools: List[str] = field(default_factory=list)
    missing: List[dict] = field(default_factory=list)
    save_wanted: bool = False
    filename: str = ""
    source: str = "rules"                  # "ai" | "rules"
    note: str = ""

    def tool_set(self, known: Optional[set] = None) -> set:
        """Tools to send with every step: the AI's pick + the core set (+ the makers when something is missing)."""
        if not self.tools:
            return set()
        chosen = set(self.tools) | CORE_TOOLS
        if self.missing:
            chosen |= MAKER_TOOLS
        return {t for t in chosen if known is None or t in known}

    def plan_text(self) -> str:
        lines = []
        if self.summary:
            lines.append(self.summary)
        if self.checklist:
            lines.append(checklist_text(self.checklist))
        if self.missing:
            lines.append("No ready tool for: " + ", ".join(f"{m.get('what')} (made with {m.get('how')})"
                                                           for m in self.missing[:6]))
        if self.save_wanted:
            lines.append(f"Save as: {self.filename or 'a .blend file'}")
        return "\n".join(lines)

    def builder_note(self) -> str:
        parts = []
        if self.checklist:
            parts.append(builder_hint(self.checklist))
        if self.missing:
            parts.append("NO READY TOOL for these parts - make them yourself with the maker tool named (python.execute "
                         "writes bpy code, mesh.create raw geometry, mesh.script a formula, build.iterate a reviewed "
                         "script): " + "; ".join(f"{m.get('what')} -> {m.get('how')}" for m in self.missing[:8]))
        if self.save_wanted:
            parts.append(f"The user wants a FILE: finish with scene.save(filename='{self.filename or 'scene.blend'}').")
        return "\n".join(parts)


def tool_catalog(definitions) -> str:
    lines = []
    for d in definitions:
        text = " ".join(str(getattr(d, "description", "")).split())
        lines.append(f"{d.name} - {text[:110]}")
    return "\n".join(lines)


def _clean_name(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()[:40]


def parse_understanding(text: str, known_tools: Optional[set] = None) -> Optional[Understanding]:
    raw = (text or "").replace("```json", "").replace("```", "")
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(re.sub(r",\s*([}\]])", r"\1", raw[start:end + 1]))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    kind = str(data.get("kind", "new")).lower()
    kind = kind if kind in ("new", "edit", "question") else "new"
    items: List[Item] = []
    for entry in (data.get("checklist") or [])[:30]:
        if not isinstance(entry, dict):
            continue
        name = _clean_name(entry.get("item"))
        if not name:
            continue
        try:
            count = max(1, min(100, int(float(entry.get("count", 1) or 1))))
        except (TypeError, ValueError):
            count = 1
        noun = name.split()[-1].replace(" ", "_")
        words = [noun] + [w for w in name.split()[:-1] if len(w) > 3] + SYNONYMS.get(noun, [])
        items.append(Item(name=name, count=count, noun=noun, position=str(entry.get("position") or "").strip()[:120],
                          words=list(dict.fromkeys(words)), size=str(entry.get("size") or "").strip()[:60]))
    tools = [str(t).strip() for t in (data.get("tools") or []) if str(t).strip()]
    if known_tools is not None:
        tools = [t for t in tools if t in known_tools]
    missing = [{"what": str(m.get("what", ""))[:80], "how": str(m.get("how", ""))[:40]}
               for m in (data.get("missing") or []) if isinstance(m, dict) and m.get("what")][:10]
    save = data.get("save") if isinstance(data.get("save"), dict) else {}
    filename = str(save.get("filename") or "").strip()
    if filename and not filename.lower().endswith(".blend"):
        filename += ".blend"
    return Understanding(kind=kind, summary=str(data.get("summary", ""))[:200], checklist=items if kind != "question"
                         else [], tools=tools, missing=missing, save_wanted=bool(save.get("wanted")),
                         filename=re.sub(r"[^\w\-. ]", "_", filename)[:80], source="ai")


def rules_understanding(request: str) -> Understanding:
    """The old way, without the AI: keyword checklist and save words."""
    from .tool_selection import wants_save
    edit = is_edit(request)
    match = re.search(r"([\w\-. ]+\.blend)\b", request or "")
    return Understanding(kind="edit" if edit else "new", checklist=[] if edit else make_checklist(request),
                         save_wanted=wants_save(request), filename=match.group(1).strip() if match else "",
                         source="rules")


def understand(ask: Callable[[str, str], str], request: str, definitions, scene_text: str = "") -> Understanding:
    """ask(system, user) -> the AI's text. Falls back to the rules when the answer is unusable."""
    known = {d.name for d in definitions}
    system = UNDERSTAND_PROMPT + tool_catalog(definitions)
    user = f"REQUEST: {request}" + (f"\n\nSCENE NOW: {scene_text[:1500]}" if scene_text else "")
    text = ask(system, user)
    found = parse_understanding(text, known)
    if found is None:
        fallback = rules_understanding(request)
        fallback.note = "the AI's plan could not be read - used the built-in rules"
        return fallback
    if not found.checklist and found.kind == "new":
        found.checklist = make_checklist(request)        # the AI listed nothing: keep at least what the words say
    return found
