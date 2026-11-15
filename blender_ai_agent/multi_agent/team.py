"""Agent team for big requests: a lead plans, specialists build, the automatic check reviews.

  lead (TeamPlanner)   one model call turns "design a modern living room with ..." into 2-6 ordered steps, each
                       owned by a role
  specialists          the normal agent loop runs each step with a role brief and only that role's tools:
                         layout     ground / room shell / big masses and where everything goes
                         modeling   the actual objects and props
                         materials  materials and colours only
                         lighting   lights, world, camera and render finish
  critic               the existing automatic check (console + vision) reviews the whole result once at the end

Small requests never use the team (one plain agent run is faster and cheaper).
"""

import json
import re
from dataclasses import dataclass
from typing import Callable, List, Optional

from ..agent.models import Message, ModelRequest

ROLES = {
    "layout": {
        "brief": "You are the LAYOUT specialist. Build the ground, room shell or base masses and decide where the main "
                 "things go (sizes, positions, spacing). Use simple placeholders only where a later step will replace "
                 "them. Do not add materials or lights.",
        "tools": ("scene.", "object.", "mesh.create", "mesh.terrain", "mesh.prism", "mesh.building", "mesh.boundary_wall",
                  "mesh.field_markings", "mesh.grandstand", "text.", "curve.", "modifier.", "library.", "asset.",
                  "template.", "material.recipe"),
    },
    "modeling": {
        "brief": "You are the MODELING specialist. Build the objects for your step with good shapes, proportions and "
                 "detail, resting exactly where the layout put them (use object.place_on / place_next_to / "
                 "snap_to_ground). Do not light the scene.",
        "tools": ("scene.", "object.", "mesh.", "curve.", "modifier.", "library.", "asset.", "character.", "build.",
                  "template.", "retopology.", "python.", "material."),
    },
    "materials": {
        "brief": "You are the MATERIALS specialist. Give every visible object of your step a fitting material "
                 "(material.recipe for real-looking surfaces, material.create/assign for simple colours). Do not "
                 "create or move objects.",
        "tools": ("scene.", "material.", "object.measure"),
    },
    "lighting": {
        "brief": "You are the LIGHTING & CAMERA specialist. Add lights (a real light next to anything that glows), "
                 "set the world, place a camera at a pleasing 3/4 angle on the main subject and finish with "
                 "render.setup. Do not create or change models.",
        "tools": ("scene.", "light.", "world.", "camera.", "render.", "vision.", "object.measure", "object.transform"),
    },
    "finish": {
        "brief": "You are the FINISHING specialist. Organise the objects into the collections the user asked for "
                 "(scene.organize), and save the file if the user asked (scene.save). Do not build anything new.",
        "tools": ("scene.", "object.measure"),
    },
}

PLANNER_PROMPT = """You lead a small 3D team in Blender. Turn the user's request into 3 to 8 ordered steps.
Roles: layout (ground / base / paths and where everything goes), modeling (the objects), materials (surfaces and
colours), lighting (lights, world, camera, render finish).

What to plan:
- Detailed request: follow every detail the user gave (names, sizes, colours, counts), nothing left out.
- Short, open request ("create a water park", "make a village"): design a believable, rich scene yourself with the
  typical elements of that place - about 10-25 objects. Example water park: main pool with rim and tiled deck, kids
  pool, 2 water slides with a tower and stairs, loungers with umbrellas, palm trees, paths, fence, snack kiosk.
- Keep one consistent ground plan in metres: the ground only a little larger than the layout, real-world sizes
  (person 1.75 m, lounger 2 m, palm tree 6-8 m), objects spread so nothing overlaps.
- Paths connect the features but never cross them: a central pond / fountain / statue sits in a plaza and the paths
  END at its rim (give the path end points at the rim). Benches, lamps, bins and trees stand BESIDE the paths
  (half the path width + 1 m from the centre-line), never on them - give positions that respect this.
- The ground is object.create PLANE + scale (or mesh.terrain), never curve.create.
- Sports grounds use real markings and sizes. Cricket: round/oval grass field (radius 45-70 m) with a light-brown
  pitch strip 20.12 x 3.05 m in the centre, a cricket_wicket at each end of the pitch (both on the strip's centre-line,
  20.12 m apart, facing each other), white crease lines, a boundary rope (thin white curve.create circle,
  thickness 0.03) just inside the field edge, 4 stadium_light masts outside the boundary with face_towards the centre,
  optional seating stands. Court / pitch lines: ONE mesh.field_markings call with the RIGHT sport (football, tennis,
  badminton, volleyball, basketball, cricket - never another sport's lines); it ALSO places the goals / wickets /
  nets / hoops at the exact spots, facing the right way - never plan them again. Sizes: football 105 x 68 m, tennis 23.77 x 10.97 m,
  badminton 13.40 x 6.10 m, volleyball 18 x 9 m, basketball 28 x 15 m. The court's length runs along X.
- Indoor courts / halls: a floor larger than the court (2-4 m run-off all round), 4 walls as object.create CUBE scaled
  to 0.3 m thick that stand OUTSIDE the run-off (never cutting through the court), a roof or ceiling, and ceiling
  lights (AREA lights) over the court. mesh.field_markings already makes the coloured court surface AND white
  lines - never paint them again or put another plane on top.
- Any seating / stand / bleachers next to a court or field: mesh.grandstand (3-6 rows for a hall), front edge 1-2 m
  outside the court's run-off, face_towards the court centre - never a single bench inside the court.
- Small sports items lie ON the floor beside the play area, never on the lines: library.place badminton_racket,
  shuttlecock. Do not build them from primitives.
- Stadiums: a mesh.grandstand on each of the 4 sides, the same rows and the same roof setting on all of them (roof
  true on all for a big stadium) so it looks symmetric; front edge 5-8 m outside the touchline, face_towards the
  pitch centre; end stands as long as the pitch is wide plus both side gaps, so the corners close. Light with 4
  stadium_light masts in the corners just outside the stands (not inside them), face_towards the centre - they
  already contain their floodlights, so the lighting step must NOT add more lights near them; it only sets the
  world/sky, render and camera.
- Buildings (hostel, hotel, college, school, office, apartment, hospital block): ONE mesh.building call per
  building - shape rect / L / U / courtyard, floors = storeys including ground (G+5 = 6), floor_height, rooms (count
  wanted), sign_text for the name board. It already makes floors, windows, balconies, railings, corridors, entrance,
  stairs, lift shafts, rooms with bed / desk / chair / wardrobe / fan and the ground-floor halls (reception,
  mess, recreation with table tennis, library, study) - never plan cubes, walls or furniture for those. Put the
  building first (layout step); later steps use the courtyard / entrance positions it returns.
- Campus extras: mesh.boundary_wall (compound wall with pillars + a gate and security cabin; sign_text = the name
  arch over the gate), library.place
  bicycle_stand / bicycle for cycle parking, courts with mesh.field_markings OUTSIDE the building footprint.
- Collections asked for -> a last "finish" step with scene.organize (and scene.save when a .blend name is given).
- Never let parts float or lean.

How to write each task (one or two sentences):
- name the objects with a shared prefix, give size and x/y position, and the best tool: library.place with one of
  these exact models: round_tree, pine_tree, palm_tree, bush, rock, park_bench, street_lamp, stadium_light,
  cricket_wicket, fence, tent, campfire, lantern, log_seat, stool, mushroom, bicycle, bicycle_parking, bed, study_table,
  chair, wardrobe, ceiling_fan, table_tennis_table, dining_table, sofa, bookshelf, reception_desk, cloud (give height in metres for the real
  size; face_towards [x, y] turns lights / benches towards a point), asset.search_local (real downloaded models), mesh.lathe (round things),
  mesh.sdf (organic / rounded), curve.create (tubes, slides, rails), curve.create profile=flat + strokes (paths,
  roads - a flat strip, never a tube), mesh.prism, material.recipe (grass, gravel, concrete, sand, water, wood_grain,
  rough_stone, foliage ...).
- Build order: layout first, then 1-3 modeling steps (group related objects), then materials, lighting last.

If the REQUEST starts with AUTOMATIC CHECK, the scene already exists and was reviewed: plan only steps that fix
the listed problems and build each MISSING element (2-5 steps, most important first); never rebuild or delete
what is already there and right.
Roles you may use: layout, modeling, materials, lighting, finish. Up to 8 steps.
Answer with JSON only: {"steps": [{"role": "layout", "task": "..."}, ...]}"""


_SCENE_WORDS = re.compile(
    r"\b(design|scene|room|interior|city|town|village|street|campus|college|school|park|garden|landscape|environment|"
    r"kitchen|bedroom|bathroom|living|office|playground|beach|forest|farm|camp|campsite|harbor|harbour|market|"
    r"stadium|zoo|museum|restaurant|cafe|shop|mall|airport|station|neighbou?rhood|world|level|map|arena|racetrack|"
    r"resort|hotel|hospital|temple|palace|castle|fort|island|amusement|waterpark|"
    r"(?:cricket|football|soccer|hockey|tennis|basketball|baseball|badminton|volleyball|rugby|golf|sports?|play|"
    r"parade|race|running|athletics|polo)\s+(?:ground|field|pitch|court|track|course|stadium|arena)|"
    r"(?:water|theme|amusement|car|skate)\s+park)\b", re.IGNORECASE)


_EDIT = re.compile(
    r"^\s*(?:please\s+)?(?:change|make (?:it|the|this|them|all)|recolou?r|colou?r|paint|modify|update|edit|replace|"
    r"swap|move|rotate|turn|resize|scale|delete|remove|rename|fix|adjust|set|increase|decrease|add more|redo)\b|"
    r"\b(?:badlo|badal\s*do|change\s*karo|kar\s*do|karo|hatao|hata\s*do|rang)\s*[.!?]*\s*$", re.IGNORECASE)


def is_edit_request(text: str) -> bool:
    """'change the roof design', 'walls ka colour badlo': a change to what exists, not a new scene."""
    text = re.sub(r"\n\(Scene context:.*?\)\s*$", "", (text or "").strip(), flags=re.DOTALL).strip()
    return len(text) < 300 and bool(_EDIT.search(text))


def is_big_request(text: str) -> bool:
    """Team mode is for whole scenes and long specs, not for one object ('make a red cube', 'make a car')
    and not for a change to what is there ('change the roof design')."""
    if is_edit_request(text):
        return False
    text = re.sub(r"\n\(Scene context:.*?\)\s*$", "", (text or "").strip(), flags=re.DOTALL).strip()
    if len(text) >= 400 or len([l for l in text.splitlines() if l.strip()]) >= 8:
        return True
    return bool(_SCENE_WORDS.search(text)) or len(text.split()) > 25


@dataclass
class TeamStep:
    role: str
    task: str


def role_filter(role: str) -> Optional[Callable[[str], bool]]:
    spec = ROLES.get(role)
    if spec is None:
        return None
    prefixes = spec["tools"]
    return lambda name: name.startswith(prefixes)


def role_brief(role: str, goal: str, task: str, number: int, total: int) -> str:
    spec = ROLES.get(role, {"brief": ""})
    return (f"TEAM MODE — step {number} of {total}. Overall goal of the user: {goal}\n"
            f"{spec['brief']}\nYour step: {task}\n"
            "Do your WHOLE step properly: build every element it lists with real proportions and enough parts that "
            "each object reads as the real thing (never one primitive standing in for a slide, a building or a "
            "tree), use the specialised tools, and keep everything on the ground or on what supports it. Precision: "
            "repeated parts (legs, posts, columns, lamps, seats) are identical in size and evenly spaced, doors and "
            "windows sit flush in their wall with door bottoms exactly on the floor, nothing your step lists is left "
            "out - check with object.measure. Many tool "
            "calls are fine. Only do your step; the other specialists do the rest - if your step only mentions where "
            "something will go later (zones, areas, space for X), do not build X. Reuse the exact names of objects "
            "that already exist. Earlier steps' results are in the scene: never rebuild what is there - a mesh.building "
            "already contains its floors, windows, balconies, rooms with furniture, halls, stairs and lifts. "
            "Finish with one short sentence about what you built.")


ROLE_SYNONYMS = {
    "layout": "layout", "planner": "layout", "architect": "layout", "architecture": "layout", "site": "layout",
    "structure": "layout", "building": "layout", "base": "layout", "ground": "layout", "terrain": "layout",
    "modeling": "modeling", "modelling": "modeling", "model": "modeling", "modeler": "modeling", "props": "modeling",
    "furniture": "modeling", "interior": "modeling", "landscape": "modeling", "landscaping": "modeling",
    "details": "modeling", "detail": "modeling", "sports": "modeling", "outdoor": "modeling", "assets": "modeling",
    "materials": "materials", "material": "materials", "texturing": "materials", "textures": "materials",
    "shading": "materials", "surfacing": "materials", "colors": "materials", "colours": "materials",
    "lighting": "lighting", "light": "lighting", "lights": "lighting", "camera": "lighting", "cameras": "lighting",
    "render": "lighting", "rendering": "lighting", "presentation": "lighting",
    "finish": "finish", "finishing": "finish", "organize": "finish", "organise": "finish", "save": "finish",
    "collections": "finish", "cleanup": "finish", "export": "finish",
}


def _role(name: str) -> str:
    key = re.sub(r"[^a-z]", "", str(name).strip().lower().split()[0] if str(name).strip() else "")
    return ROLE_SYNONYMS.get(key, key if key in ROLES else "")


def parse_plan(text: str, max_steps: int = 8) -> List[TeamStep]:
    """Read the lead's plan. Tolerates code fences, trailing commas, other role words and a cut-off answer."""
    text = (text or "").replace("```json", "").replace("```", "")
    items = []
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        chunk = re.sub(r",\s*([}\]])", r"\1", text[start:end + 1])
        try:
            data = json.loads(chunk)
            items = (data.get("steps") or []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        except ValueError:
            items = []
    if not items:                                    # salvage complete {"role": ..., "task": ...} objects
        for role, task in re.findall(r'"role"\s*:\s*"([^"]+)"\s*,\s*"task"\s*:\s*"((?:[^"\\]|\\.)*)"', text):
            try:
                task = json.loads(f'"{task}"')
            except ValueError:
                pass
            items.append({"role": role, "task": task})
    steps: List[TeamStep] = []
    for item in items[:max_steps]:
        if not isinstance(item, dict):
            continue
        role = _role(item.get("role", ""))
        task = re.sub(r"\s+", " ", str(item.get("task", ""))).strip()
        if role and len(task) >= 6:
            steps.append(TeamStep(role, task[:700]))
    return steps


_SECTION = re.compile(r"^\s*(?:#+\s*|\*\*\s*)?(?:\d+[.)]|[IVX]+[.)])\s*(.+?)(?:\*\*)?\s*$", re.MULTILINE)
_ROLE_WORDS = (
    ("finish", r"collection|save|\.blend|organi[sz]e|technical requirement|export"),
    ("lighting", r"light|camera|render|presentation|sky|hdri|sun"),
    ("materials", r"material|texture|colou?r|pbr|shader"),
    ("layout", r"main building|building|layout|structure|site|architect|footprint|ground"),
)


def fallback_plan(request: str) -> List[TeamStep]:
    """When the lead's answer is unusable: one step per numbered section of a long spec (role from its words),
    else the standard layout -> modeling -> materials -> lighting run over the whole request."""
    text = re.sub(r"\n\(Scene context:.*?\)\s*$", "", request or "", flags=re.DOTALL)
    heads = list(_SECTION.finditer(text))
    steps: List[TeamStep] = []
    if len(heads) >= 3:
        for i, head in enumerate(heads):
            body = text[head.start():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
            title = head.group(1).strip(" *:")
            task = re.sub(r"\s+", " ", body.replace("**", "")).strip()
            if re.search(r"architectur\w* detail|proportion|guideline|general|notes?\b|constraint", title, re.IGNORECASE):
                target = next((st for st in steps if st.role == "layout"), steps[0] if steps else None)
                if target is not None:                # advice for the building, not a step of its own
                    target.task = (target.task + " " + task)[:900]
                    continue
            roles = []
            for name, pattern in _ROLE_WORDS:
                if re.search(pattern, title, re.IGNORECASE):
                    roles.append(name)
            if "finish" in roles:
                roles = ["finish"]
            elif "layout" in roles and len(roles) > 1:
                roles.remove("layout")
            for role in roles or ["modeling"]:
                steps.append(TeamStep(role, task[:900]))
        order = {"layout": 0, "modeling": 1, "materials": 2, "lighting": 3, "finish": 4}
        steps.sort(key=lambda st: order.get(st.role, 1))
        return steps[:8]
    brief = re.sub(r"\s+", " ", text).strip()[:500]
    return [TeamStep("layout", f"Build the ground, the main masses / buildings and where everything goes for: {brief}"),
            TeamStep("modeling", f"Build every object and detail the request lists, at real size: {brief}"),
            TeamStep("materials", "Give every visible object a fitting realistic material (material.recipe)."),
            TeamStep("lighting", "Light the scene (sun / sky or fitting lights), place the camera on the whole result "
                                 "and finish with render.setup.")]


class TeamPlanner:
    """Asks the model (strong tier when routing is on) for the step plan. Returns [] if the plan is unusable."""

    def __init__(self, provider_getter: Callable[[], object], scene_summary: Optional[Callable[[], str]] = None):
        self._provider_getter = provider_getter
        self._scene_summary = scene_summary
        self.last_raw = ""
        self.last_source = ""

    def plan(self, request: str) -> List[TeamStep]:
        provider = self._provider_getter()
        if provider is None:
            return []
        begin_task = getattr(provider, "begin_task", None)
        if callable(begin_task):
            begin_task(request)
        scene = ""
        if self._scene_summary is not None:
            try:
                scene = self._scene_summary() or ""
            except Exception:  # noqa: BLE001
                scene = ""
        user = f"REQUEST: {request}" + (f"\n\n{scene}" if scene else "")
        self.last_raw, self.last_source = "", "lead"
        try:
            response = provider.generate(ModelRequest(messages=[Message(role="system", content=PLANNER_PROMPT),
                                                                Message(role="user", content=user)], temperature=0.3))
            self.last_raw = getattr(response, "content", "") or ""
        except Exception as exc:  # noqa: BLE001
            from ..reliability.friendly_errors import is_quota_error
            if is_quota_error(str(exc)):
                raise
            self.last_raw = f"(planner error: {exc})"
        steps = parse_plan(self.last_raw)
        if len(steps) >= 2:
            return steps
        self.last_source = "fallback"
        return fallback_plan(request)
