"""mesh.grandstand: stepped spectator seating for stadiums, courts and arenas.

Local frame: the stand runs along X (centred on the origin), the front edge (lowest row, next to
the field) lies on y = 0 and the rows climb towards +Y. Its front therefore faces -Y; `face_towards`
turns it to look at a point (the field centre).
"""

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .base import Permission, Tool, ToolResult
from .models import _coerce_bool, _coerce_list, _coerce_number, _vec3

Box = Tuple[float, float, float, float, float, float]          # x0, x1, y0, y1, z0, z1


def _box_mesh(boxes: List[Box]):
    verts, faces = [], []
    for x0, x1, y0, y1, z0, z1 in boxes:
        b = len(verts)
        verts += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                  (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        faces += [(b, b + 3, b + 2, b + 1), (b + 4, b + 5, b + 6, b + 7), (b, b + 1, b + 5, b + 4),
                  (b + 1, b + 2, b + 6, b + 5), (b + 2, b + 3, b + 7, b + 6), (b + 3, b, b + 4, b + 7)]
    return [tuple(round(c, 4) for c in v) for v in verts], faces


def grandstand_parts(length: float, rows: int, row_depth: float = 0.8, row_rise: float = 0.4,
                     front_height: float = 1.2, seats: bool = True, roof: bool = False, aisle_every: float = 12.0):
    """Boxes for the stepped body, the seat rows and the roof (+ its columns)."""
    half = length / 2.0
    body: List[Box] = []
    for i in range(rows):
        top = front_height + i * row_rise
        body.append((-half, half, i * row_depth, (i + 1) * row_depth, 0.0, top))
    back_y = rows * row_depth
    top_row = front_height + (rows - 1) * row_rise
    body.append((-half, half, back_y, back_y + 0.35, 0.0, top_row + 1.2))              # back wall
    body.append((-half - 0.35, -half, 0.0, back_y + 0.35, 0.0, top_row + 1.2))         # side walls
    body.append((half, half + 0.35, 0.0, back_y + 0.35, 0.0, top_row + 1.2))

    seat_boxes: List[Box] = []
    if seats:
        aisles = max(0, int(length // aisle_every))
        gaps = [(-half + (k + 1) * length / (aisles + 1)) for k in range(aisles)]
        edges = [-half + 0.3] + [v for g in gaps for v in (g - 0.6, g + 0.6)] + [half - 0.3]
        for i in range(rows):
            z = front_height + i * row_rise
            y0 = i * row_depth + 0.12
            for x0, x1 in zip(edges[0::2], edges[1::2]):
                if x1 - x0 > 0.5:
                    seat_boxes.append((x0, x1, y0, y0 + 0.42, z, z + 0.42))

    roof_boxes: List[Box] = []
    if roof:
        roof_z = top_row + 4.0
        roof_boxes.append((-half - 0.5, half + 0.5, back_y * 0.15, back_y + 0.6, roof_z, roof_z + 0.35))
        columns = max(2, int(length // 15) + 1)
        for k in range(columns):
            x = -half + 0.4 + k * (length - 0.8) / (columns - 1)
            roof_boxes.append((x - 0.25, x + 0.25, back_y + 0.05, back_y + 0.55, 0.0, roof_z))

    return body, seat_boxes, roof_boxes, {"depth": round(back_y + 0.35, 2), "height": round(top_row + (4.35 if roof else 1.2), 2)}


@dataclass
class GrandstandInput:
    name: str = "stand"
    length: float = 40.0
    rows: int = 15
    row_depth: float = 0.8
    row_rise: float = 0.4
    front_height: float = 1.2
    seats: bool = True
    roof: bool = False
    location: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    yaw_degrees: float = 0.0
    face_towards: Optional[List[float]] = None

    def __post_init__(self):
        self.name = str(self.name or "stand").strip() or "stand"
        self.length = _coerce_number(self.length, "GrandstandInput.length")
        if not (3.0 <= self.length <= 400.0):
            raise ValueError("GrandstandInput.length must be 3-400 metres")
        self.rows = int(_coerce_number(self.rows, "GrandstandInput.rows"))
        if not (1 <= self.rows <= 80):
            raise ValueError("GrandstandInput.rows must be 1-80")
        for attr, lo, hi in (("row_depth", 0.5, 2.0), ("row_rise", 0.1, 1.0), ("front_height", 0.0, 10.0)):
            value = _coerce_number(getattr(self, attr), f"GrandstandInput.{attr}")
            if not (lo <= value <= hi):
                raise ValueError(f"GrandstandInput.{attr} must be {lo}-{hi}")
            setattr(self, attr, value)
        self.seats = _coerce_bool(self.seats, "GrandstandInput.seats")
        self.roof = _coerce_bool(self.roof, "GrandstandInput.roof")
        self.location = _vec3(self.location, "GrandstandInput.location")
        self.yaw_degrees = _coerce_number(self.yaw_degrees, "GrandstandInput.yaw_degrees")
        if self.face_towards is not None:
            target = _coerce_list(self.face_towards, "GrandstandInput.face_towards")
            if len(target) not in (2, 3):
                raise ValueError("GrandstandInput.face_towards must be [x, y]")
            self.face_towards = target[:2]


class MeshGrandstandTool(Tool):
    name = "mesh.grandstand"
    description = (
        "Builds a stepped spectator stand (grandstand / bleachers) for stadiums, courts and arenas in ONE call: the "
        "stepped concrete body (`name`), the seat rows as a separate object (`name`_seats, give it a team colour) and "
        "optionally a roof on columns (`name`_roof). length = along the field; rows x row_depth = how far back it goes; "
        "rows x row_rise = how high. location = the FRONT-CENTRE of the stand at ground level (put it a few metres "
        "outside the touchline); face_towards [x, y] = the field centre turns it to face the field. Use one per side."
    )
    permission = Permission.SAFE_WRITE
    input_model = GrandstandInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, v: GrandstandInput) -> ToolResult:
        yaw = v.yaw_degrees
        if v.face_towards is not None:
            fx, fy = v.face_towards[0] - v.location[0], v.face_towards[1] - v.location[1]
            if abs(fx) + abs(fy) > 1e-6:
                yaw = math.degrees(math.atan2(fy, fx) - math.atan2(-1.0, 0.0))     # front is -Y
        rotation = [0.0, 0.0, math.radians(yaw)]
        body, seat_boxes, roof_boxes, size = grandstand_parts(v.length, v.rows, v.row_depth, v.row_rise,
                                                              v.front_height, v.seats, v.roof)
        created = []
        for suffix, boxes in (("", body), ("_seats", seat_boxes), ("_roof", roof_boxes)):
            if not boxes:
                continue
            verts, faces = _box_mesh(boxes)
            obj = self._bridge.create_mesh(name=f"{v.name}{suffix}", vertices=verts, faces=faces,
                                           location=v.location, rotation=rotation, scale=[1.0, 1.0, 1.0])
            created.append(obj.name)
        return ToolResult.ok({
            "objects": created, "length": v.length, "depth": size["depth"], "height": size["height"],
            "yaw_degrees": round(yaw, 1), "location": list(v.location),
            "note": "Colour the body with material.recipe concrete and the _seats object with a bright colour.",
        })
