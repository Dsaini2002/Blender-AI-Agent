"""mesh.field_markings: every regulation line of a football pitch, tennis court or cricket square
in one call, with exact sizes. Hand-drawn boxes came out the wrong size (a 16.5 x 16.5 m penalty
area), in the wrong place and with rounded corners.

Local frame: the field is centred on the origin with its LENGTH along X. Lines are thin flat strips
just above the grass. The result also gives the spots where goals / wickets belong.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .base import Permission, Tool, ToolResult
from .models import _coerce_list, _coerce_number, _vec3
from .ribbon import ribbon_mesh

Point = Tuple[float, float]


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, steps: int = 48) -> List[Point]:
    return [(cx + r * math.cos(a0 + (a1 - a0) * i / steps), cy + r * math.sin(a0 + (a1 - a0) * i / steps))
            for i in range(steps + 1)]


def _circle(cx: float, cy: float, r: float, steps: int = 64) -> List[Point]:
    pts = _arc(cx, cy, r, 0.0, 2 * math.pi, steps)
    return pts[:-1] + [pts[0]]


def _rect(x0: float, y0: float, x1: float, y1: float) -> List[Point]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def football_lines(length: float = 105.0, width: float = 68.0):
    L, W = length / 2.0, width / 2.0
    lines: List[List[Point]] = [_rect(-L, -W, L, W), [(0.0, -W), (0.0, W)], _circle(0.0, 0.0, 9.15)]
    spots: List[Tuple[Point, float]] = [((0.0, 0.0), 0.11)]
    for s in (1.0, -1.0):
        gx = s * L
        pa = s * (L - 16.5)
        lines.append([(gx, -20.16), (pa, -20.16), (pa, 20.16), (gx, 20.16)])                     # penalty area
        ga = s * (L - 5.5)
        lines.append([(gx, -9.16), (ga, -9.16), (ga, 9.16), (gx, 9.16)])                         # goal area
        px = s * (L - 11.0)
        spots.append(((px, 0.0), 0.11))                                                          # penalty spot
        half = math.acos(min(1.0, (16.5 - 11.0) / 9.15))                                         # arc outside the box
        centre = math.pi if s > 0 else 0.0
        lines.append(_arc(px, 0.0, 9.15, centre - half, centre + half, 32))                     # penalty arc
    for sx in (1.0, -1.0):                                                                       # corner arcs
        for sy in (1.0, -1.0):
            a = math.atan2(-sy, -sx)
            lines.append(_arc(sx * L, sy * W, 1.0, a - math.pi / 4, a + math.pi / 4, 12))
    anchors = {"goal_centres": [[L, 0.0], [-L, 0.0]], "goal_face_towards": [0.0, 0.0],
               "corners": [[L, W], [L, -W], [-L, W], [-L, -W]]}
    return lines, spots, anchors


def tennis_lines(length: float = 23.77, width: float = 10.97):
    L, W = length / 2.0, width / 2.0
    S = W * (8.23 / 10.97)                                     # singles side lines, in proportion to the court
    service = L * (6.40 / 11.885)                              # service lines 6.40 m from the net
    lines = [_rect(-L, -W, L, W), [(-L, -S), (L, -S)], [(-L, S), (L, S)],
             [(-service, -S), (-service, S)], [(service, -S), (service, S)], [(-service, 0.0), (service, 0.0)],
             [(-L, 0.0), (-L + 0.1, 0.0)], [(L, 0.0), (L - 0.1, 0.0)]]
    anchors = {"net_line": [[0.0, -W - 0.914], [0.0, W + 0.914]], "net_height_m": 0.914,
               "net_centre": [[0.0, 0.0]], "net_model": "tennis_net"}
    return lines, [], anchors


def badminton_lines(length: float = 13.40, width: float = 6.10):
    L, W = length / 2.0, width / 2.0
    S = W * (5.18 / 6.10)                                      # singles side lines
    short = 1.98 * length / 13.40                              # short service lines, 1.98 m from the net
    long_d = L - 0.76 * length / 13.40                         # doubles long service lines, 0.76 m inside the back
    lines = [_rect(-L, -W, L, W), [(-L, -S), (L, -S)], [(-L, S), (L, S)],
             [(-short, -W), (-short, W)], [(short, -W), (short, W)],
             [(-long_d, -W), (-long_d, W)], [(long_d, -W), (long_d, W)],
             [(short, 0.0), (L, 0.0)], [(-short, 0.0), (-L, 0.0)]]
    anchors = {"net_centre": [[0.0, 0.0]], "net_model": "badminton_net", "net_height_m": 1.55,
               "net_post_spots": [[0.0, -W], [0.0, W]]}
    return lines, [], anchors


def volleyball_lines(length: float = 18.0, width: float = 9.0):
    L, W = length / 2.0, width / 2.0
    attack = 3.0 * length / 18.0
    lines = [_rect(-L, -W, L, W), [(0.0, -W), (0.0, W)], [(-attack, -W), (-attack, W)], [(attack, -W), (attack, W)]]
    anchors = {"net_centre": [[0.0, 0.0]], "net_model": "volleyball_net", "net_height_m": 2.43}
    return lines, [], anchors


def _three_point_arc(hx: float, s: float, a: float) -> List[Point]:
    """The 6.75 m arc around the basket at hx, on the court side (towards the centre), meeting the corner lines."""
    # angle measured from the +X axis; the court side is towards -s
    toward_centre = math.pi if s > 0 else 0.0
    half = math.pi / 2 - a          # the arc meets the corner lines at y = +-corner
    return _arc(hx, 0.0, 6.75, toward_centre - half, toward_centre + half, 64)


def basketball_lines(length: float = 28.0, width: float = 15.0):
    L, W = length / 2.0, width / 2.0
    lines: List[List[Point]] = [_rect(-L, -W, L, W), [(0.0, -W), (0.0, W)], _circle(0.0, 0.0, 1.8)]
    hoops = []
    for s in (1.0, -1.0):
        base = s * L
        ft = s * (L - 5.8)                                     # free-throw line 5.8 m from the baseline
        lines.append([(base, -2.45), (ft, -2.45), (ft, 2.45), (base, 2.45)])    # the key (4.9 m wide)
        lines.append(_circle(ft, 0.0, 1.8))                                       # free-throw circle
        hx = s * (L - 1.575)                                                      # basket centre
        corner = min(6.6, W - 0.9)
        dx = math.sqrt(max(0.0, 6.75 ** 2 - corner ** 2))
        meet = hx - s * dx
        lines.append([(base, -corner), (meet, -corner)])                         # three-point corners
        lines.append([(base, corner), (meet, corner)])
        a = math.acos(corner / 6.75)
        # three-point arc: from one corner line round the basket to the other
        lines.append(_three_point_arc(hx, s, a))
        hoops.append([s * (L + 1.0), 0.0])
    anchors = {"hoop_pole_spots": hoops, "hoop_face_towards": [0.0, 0.0], "hoop_model": "basketball_hoop",
               "rim_height_m": 3.05}
    return lines, [], anchors


def cricket_lines(length: float = 20.12, width: float = 3.05, boundary_radius: float = 0.0):
    half = length / 2.0                                       # stumps are 20.12 m apart
    lines: List[List[Point]] = []
    for s in (1.0, -1.0):
        sx = s * half
        px = s * (half - 1.22)                                 # popping crease 1.22 m in front of the stumps
        lines.append([(sx, -1.32), (sx, 1.32)])               # bowling crease
        lines.append([(px, -1.83), (px, 1.83)])               # popping crease
        lines.append([(px, -1.32), (s * (half + 1.22), -1.32)])   # return creases
        lines.append([(px, 1.32), (s * (half + 1.22), 1.32)])
    if boundary_radius > 0:
        lines.append(_circle(0.0, 0.0, boundary_radius, 128))
    anchors = {"wicket_centres": [[half, 0.0], [-half, 0.0]], "wicket_face_towards": [0.0, 0.0],
               "pitch_strip_size_m": [length + 2.0, width]}
    return lines, [], anchors


SPORTS = {"football": football_lines, "soccer": football_lines, "tennis": tennis_lines, "cricket": cricket_lines,
          "badminton": badminton_lines, "volleyball": volleyball_lines, "basketball": basketball_lines}
# Court surface under the lines: (run-off margin in metres, recipe, params). None = no surface (football and
# cricket grounds get their grass from the ground itself; cricket gets the pitch strip below).
SURFACES = {
    "badminton": (1.0, "paint", {"color": [0.05, 0.32, 0.18, 1.0], "roughness": 0.6}),
    "tennis": (3.0, "paint", {"color": [0.12, 0.27, 0.52, 1.0], "roughness": 0.7}),
    "volleyball": (2.0, "paint", {"color": [0.78, 0.36, 0.12, 1.0], "roughness": 0.6}),
    "basketball": (2.0, "wood_grain", {"light": [0.72, 0.5, 0.28, 1.0], "dark": [0.55, 0.35, 0.18, 1.0], "scale": 6.0}),
    "cricket": (0.0, "dirt_ground", {"color": [0.62, 0.52, 0.34, 1.0], "scale": 6.0}),
}
LINE_WIDTH = {"football": 0.12, "soccer": 0.12, "tennis": 0.05, "cricket": 0.05, "badminton": 0.04,
              "volleyball": 0.05, "basketball": 0.05}


@dataclass
class FieldMarkingsInput:
    sport: str = "football"
    name: str = ""
    length: Optional[float] = None
    width: Optional[float] = None
    line_width: Optional[float] = None
    boundary_radius: float = 0.0
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    yaw_degrees: float = 0.0
    surface: Optional[bool] = None
    surface_color: Optional[List[float]] = None
    equipment: bool = True

    def __post_init__(self):
        self.sport = str(self.sport or "football").strip().lower()
        if self.sport not in SPORTS:
            raise ValueError(f"FieldMarkingsInput.sport must be one of {sorted(SPORTS)}")
        self.name = str(self.name or f"{self.sport}_lines").strip()
        for attr in ("length", "width", "line_width"):
            value = getattr(self, attr)
            if value is not None:
                value = _coerce_number(value, f"FieldMarkingsInput.{attr}")
                if value <= 0:
                    raise ValueError(f"FieldMarkingsInput.{attr} must be positive")
                setattr(self, attr, value)
        self.boundary_radius = _coerce_number(self.boundary_radius, "FieldMarkingsInput.boundary_radius")
        if self.surface is not None:
            self.surface = str(self.surface).strip().lower() not in ("false", "0", "no", "none", "off", "")
        if self.surface_color is not None:
            color = _coerce_list(self.surface_color, "FieldMarkingsInput.surface_color")
            if len(color) not in (3, 4):
                raise ValueError("FieldMarkingsInput.surface_color must be [r, g, b] (0-1)")
            self.surface_color = (color + [1.0])[:4]
        self.location = _vec3(self.location, "FieldMarkingsInput.location")
        self.yaw_degrees = _coerce_number(self.yaw_degrees, "FieldMarkingsInput.yaw_degrees")
        self.equipment = str(self.equipment).strip().lower() not in ("false", "0", "no", "none", "off", "")


def markings_mesh(v: FieldMarkingsInput):
    builder = SPORTS[v.sport]
    kwargs = {}
    if v.length:
        kwargs["length"] = v.length
    if v.width:
        kwargs["width"] = v.width
    if v.sport == "cricket" and v.boundary_radius > 0:
        kwargs["boundary_radius"] = v.boundary_radius
    lines, spots, anchors = builder(**kwargs)
    line_width = v.line_width or LINE_WIDTH.get(v.sport, 0.05)
    verts, faces = [], []
    for line in lines:
        closed = len(line) > 3 and math.dist(line[0], line[-1]) < 1e-6
        pts = [(x, y, 0.0) for x, y in (line[:-1] if closed else line)]
        lv, lf = ribbon_mesh(pts, line_width, depth=0.01, closed=closed, base_index=len(verts))
        verts += lv
        faces += lf
    for (x, y), r in spots:
        lv, lf = ribbon_mesh([(x + r * 0.5 * math.cos(a), y + r * 0.5 * math.sin(a), 0.0)
                              for a in [2 * math.pi * i / 16 for i in range(16)]], r, depth=0.01, closed=True,
                             base_index=len(verts))
        verts += lv
        faces += lf
    return verts, faces, anchors, line_width


def _place(point, location, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    return [round(location[0] + point[0] * c - point[1] * s, 3), round(location[1] + point[0] * s + point[1] * c, 3)]


class FieldMarkingsTool(Tool):
    name = "mesh.field_markings"
    description = (
        "Draws ALL regulation lines of a sports field in one call, with exact sizes and sharp corners: sport = "
        "football (105 x 68 m: touchlines, halfway line, centre circle and spot, penalty and goal areas, penalty spots "
        "and arcs, corner arcs), tennis (23.77 x 10.97 m), badminton (13.40 x 6.10 m: doubles + singles lines, short "
        "and long service lines, centre lines), volleyball (18 x 9 m), basketball (28 x 15 m: key, free-throw circles, "
        "three-point lines) or cricket (creases 20.12 m apart; boundary_radius adds the boundary circle). Never use "
        "one sport's lines for another. Leave length/width out for the regulation size. The "
        "field is centred on `location` with its length along X (turn it with yaw_degrees). Put it 0.01-0.02 m above "
        "the floor. It ALSO builds the coloured court surface under the lines (`name`_surface: green for badminton, "
        "blue tennis, orange volleyball, wooden basketball, a clay pitch strip for cricket; surface_color overrides, "
        "surface=false skips it) and paints the lines white - do not recolour them. The result gives the exact goal / "
        "wicket / net / hoop positions and the library model to place there (football_goal, cricket_wicket, "
        "badminton_net, tennis_net, volleyball_net, basketball_hoop) - and it PLACES them there itself (equipment=false "
        "skips that), so never place them again."
    )
    permission = Permission.SAFE_WRITE
    input_model = FieldMarkingsInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: FieldMarkingsInput) -> ToolResult:
        verts, faces, anchors, line_width = markings_mesh(v)
        yaw = math.radians(v.yaw_degrees)
        surface_name = self._surface(v, yaw)
        obj = self._bridge.create_mesh(name=v.name, vertices=verts, faces=faces, location=v.location,
                                       rotation=[0.0, 0.0, yaw], scale=[1.0, 1.0, 1.0])
        line_mat = _paint(self._bridge, f"{v.name}_white", "paint", {"color": [0.95, 0.95, 0.95, 1.0], "roughness": 0.5})
        if line_mat:
            self._bridge.assign_material(obj.name, line_mat)
        placed: Dict[str, object] = {}
        for key, value in anchors.items():
            if isinstance(value, list) and value and isinstance(value[0], list):
                placed[key] = [_place(p, v.location, yaw) for p in value]
            elif isinstance(value, list) and len(value) == 2 and all(isinstance(c, (int, float)) for c in value) \
                    and key.endswith("face_towards"):
                placed[key] = _place(value, v.location, yaw)
            else:
                placed[key] = value
        data = {"name": obj.name, "sport": v.sport, "line_width": line_width, "faces": len(faces), **placed}
        if surface_name:
            data["surface"] = surface_name
        equipment = self._equipment(v, placed) if v.equipment else []
        if equipment:
            data["equipment"] = equipment
        data["note"] = ("The lines are already white" + (f" and '{surface_name}' is the coloured court surface" if surface_name
                        else "") + " - do not recolour them. Put the floor / grass under them, not on top." +
                        (" The " + ", ".join(sorted({e['model'] for e in equipment})) + " already stand in the right "
                         "places - do not place them again." if equipment else ""))
        return ToolResult.ok(data)

    def _equipment(self, v: FieldMarkingsInput, placed: Dict[str, object]) -> List[dict]:
        """Goals / wickets / nets / hoops from the model library at their exact spots, facing the right way."""
        from .library_tools import LibraryPlaceTool, load_library

        library = load_library()
        sets = []
        if placed.get("goal_centres"):
            sets.append(("football_goal", placed["goal_centres"], placed.get("goal_face_towards")))
        if placed.get("wicket_centres"):
            sets.append(("cricket_wicket", placed["wicket_centres"], placed.get("wicket_face_towards")))
        if placed.get("hoop_pole_spots"):
            sets.append((placed.get("hoop_model") or "basketball_hoop", placed["hoop_pole_spots"],
                         placed.get("hoop_face_towards")))
        if placed.get("net_centre") and placed.get("net_model"):
            sets.append((placed["net_model"], placed["net_centre"], None))
        ground = max(0.0, v.location[2] - 0.015) if v.location[2] < 0.1 else v.location[2] - 0.015
        tool = LibraryPlaceTool(self._bridge)
        out = []
        for model, spots, face in sets:
            if model not in library:
                continue
            for i, (x, y) in enumerate(spots):
                args = {"model": model, "location": [x, y, ground], "prefix": f"{v.name}_{model}{i + 1}_"}
                if face is not None:
                    args["face_towards"] = list(face)
                else:
                    args["yaw_degrees"] = v.yaw_degrees
                result = tool.execute(args)
                if result.success:
                    out.append({"model": model, "location": [x, y], "prefix": args["prefix"]})
        if out:
            remember_court(v, placed, {e["model"] for e in out})
        return out

    def _surface(self, v: FieldMarkingsInput, yaw: float) -> Optional[str]:
        """The coloured court (green badminton mat, blue tennis court ...) just under the lines."""
        wanted = v.surface if v.surface is not None else v.sport in SURFACES
        if not wanted or v.sport not in SURFACES and v.surface_color is None:
            return None
        margin, recipe, params = SURFACES.get(v.sport, (1.0, "paint", {}))
        builder = SPORTS[v.sport]
        kwargs = {k: getattr(v, k) for k in ("length", "width") if getattr(v, k)}
        _, _, anchors = builder(**kwargs)
        if v.sport == "cricket":
            length, width = anchors.get("pitch_strip_size_m", [22.12, 3.05])
        else:
            lines, _, _ = builder(**kwargs)
            length = 2 * max(abs(p[0]) for line in lines for p in line)
            width = 2 * max(abs(p[1]) for line in lines for p in line)
        hx, hy = length / 2.0 + margin, width / 2.0 + margin
        verts = [(-hx, -hy, -0.012), (hx, -hy, -0.012), (hx, hy, -0.012), (-hx, hy, -0.012),
                 (-hx, -hy, -0.002), (hx, -hy, -0.002), (hx, hy, -0.002), (-hx, hy, -0.002)]
        faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        obj = self._bridge.create_mesh(name=f"{v.name}_surface", vertices=verts, faces=faces, location=v.location,
                                       rotation=[0.0, 0.0, yaw], scale=[1.0, 1.0, 1.0])
        params = dict(params)
        if v.surface_color is not None:
            params = {"color": v.surface_color, "roughness": 0.6}
            recipe = "paint"
        mat = _paint(self._bridge, f"{v.name}_surface_mat", recipe, params)
        if mat:
            self._bridge.assign_material(obj.name, mat)
        return obj.name


def _paint(bridge, name: str, recipe: str, params: dict) -> Optional[str]:
    """A material from a recipe (node material) or, on a simple bridge, a plain colour."""
    if hasattr(bridge, "build_node_material"):
        try:
            from .shader_nodes import build_recipe
            return bridge.build_node_material(name, build_recipe(recipe, params), True)["name"]
        except Exception:  # noqa: BLE001
            pass
    color = list(params.get("color") or params.get("light") or [0.9, 0.9, 0.9, 1.0])
    try:
        return bridge.create_material(name=name, color=(color + [1.0])[:4]).name
    except Exception:  # noqa: BLE001
        return None


# Courts made in this session -> what already stands on them (library.place skips a second net / hoop there).
COURTS: Dict[str, dict] = {}


def remember_court(v: "FieldMarkingsInput", placed: Dict[str, object], models) -> None:
    lines, _, _ = SPORTS[v.sport](**{k: getattr(v, k) for k in ("length", "width") if getattr(v, k)})
    hx = max(abs(p[0]) for line in lines for p in line) if lines else 10.0
    hy = max(abs(p[1]) for line in lines for p in line) if lines else 10.0
    COURTS[v.name] = {"centre": list(v.location[:2]), "half": [hx, hy], "yaw": math.radians(v.yaw_degrees),
                      "models": set(models)}


def court_with(model: str, x: float, y: float, bridge=None, margin: float = 4.0) -> Optional[str]:
    """Name of a court that already has `model` and contains (x, y) (with a margin), if any."""
    for name, court in list(COURTS.items()):
        if model not in court["models"]:
            continue
        if bridge is not None and hasattr(bridge, "get_object"):
            try:
                if bridge.get_object(name) is None:
                    COURTS.pop(name, None)
                    continue
            except Exception:  # noqa: BLE001
                pass
        dx, dy = x - court["centre"][0], y - court["centre"][1]
        c, s = math.cos(-court["yaw"]), math.sin(-court["yaw"])
        lx, ly = dx * c - dy * s, dx * s + dy * c
        if abs(lx) <= court["half"][0] + margin and abs(ly) <= court["half"][1] + margin:
            return name
    return None
