"""mesh_damage.py
==============

Regions: top, bottom, left, right, front, back (world axes) ya all.
"""

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

REGIONS = ("top", "bottom", "left", "right", "front", "back", "all")
STYLES = ("broken", "chipped", "dented", "rough")

_REGION_AXIS = {
    "top": (2, +1), "bottom": (2, -1),
    "right": (0, +1), "left": (0, -1),
    "back": (1, +1), "front": (1, -1),
}

Vec = Tuple[float, float, float]


@dataclass
class DamagePlan:
    moves: Dict[int, Vec] = field(default_factory=dict)
    remove_faces: List[int] = field(default_factory=list)
    affected: int = 0


def _bounds(vertices: Sequence[Vec]):
    mins = [min(v[i] for v in vertices) for i in range(3)]
    maxs = [max(v[i] for v in vertices) for i in range(3)]
    return mins, maxs


def region_vertex_indices(vertices: Sequence[Vec], region: str = "top", portion: float = 0.25) -> Dict[int, float]:
    if not vertices:
        return {}
    if region == "all" or region not in _REGION_AXIS:
        return {i: 1.0 for i in range(len(vertices))}

    axis, sign = _REGION_AXIS[region]
    mins, maxs = _bounds(vertices)
    span = maxs[axis] - mins[axis]
    if span <= 1e-9:
        return {i: 1.0 for i in range(len(vertices))}

    portion = max(0.02, min(1.0, portion))
    result = {}
    for index, vertex in enumerate(vertices):
        t = (vertex[axis] - mins[axis]) / span
        if sign > 0 and t >= 1.0 - portion:
            result[index] = (t - (1.0 - portion)) / portion
        elif sign < 0 and t <= portion:
            result[index] = 1.0 - t / portion
    return result


def _normalize(x: float, y: float):
    length = math.hypot(x, y)
    return (x / length, y / length) if length > 1e-12 else (0.0, 0.0)


def plan_damage(vertices: Sequence[Vec], faces: Sequence[Sequence[int]], region: str = "top", portion: float = 0.25,
                strength: float = 0.15, style: str = "broken", seed: int = 1) -> DamagePlan:
    plan = DamagePlan()
    if not vertices:
        return plan

    rng = random.Random(seed)
    strength = max(0.01, min(0.6, strength))
    depths = region_vertex_indices(vertices, region, portion)
    plan.affected = len(depths)
    if not depths:
        return plan

    mins, maxs = _bounds(vertices)
    extent = [maxs[i] - mins[i] for i in range(3)]
    size = max(max(extent), 1e-6)
    axis, sign = _REGION_AXIS.get(region, (2, +1))
    height = max(extent[axis], size * 0.05)
    t1, t2 = [i for i in range(3) if i != axis]

    ring = list(depths)
    centre1 = sum(vertices[i][t1] for i in ring) / len(ring)
    centre2 = sum(vertices[i][t2] for i in ring) / len(ring)

    def inward_axis(vertex: Vec, amount: float) -> List[float]:
        moved = list(vertex)
        moved[axis] -= sign * amount
        return moved

    if style == "broken":
        teeth = rng.randint(5, 9)
        tooth_depth = [rng.uniform(0.25, 1.0) for _ in range(teeth)]
        for index, depth in depths.items():
            vertex = vertices[index]
            theta = math.atan2(vertex[t2] - centre2, vertex[t1] - centre1)
            position = ((theta + math.pi) / (2 * math.pi)) * teeth
            tooth, fraction = int(position) % teeth, position - int(position)
            triangle = 1.0 - abs(2.0 * fraction - 1.0)
            drop = strength * height * (0.2 + 0.8 * tooth_depth[tooth] * (1.0 - 0.85 * triangle)) * depth ** 1.2
            moved = inward_axis(vertex, drop)
            jitter = 0.02 * size * depth
            moved[t1] += rng.uniform(-jitter, jitter)
            moved[t2] += rng.uniform(-jitter, jitter)
            plan.moves[index] = tuple(moved)
        for face_index, face in enumerate(faces):
            if face and all(v in depths for v in face):
                mean_depth = sum(depths[v] for v in face) / len(face)
                if mean_depth >= 0.6 and rng.random() < 0.3:
                    plan.remove_faces.append(face_index)

    elif style == "chipped":
        chosen = rng.sample(ring, max(1, int(len(ring) * 0.2)))
        for index in chosen:
            depth = depths[index]
            plan.moves[index] = tuple(inward_axis(vertices[index], strength * height * 0.5 * depth))
        chosen_set = set(chosen)
        for face_index, face in enumerate(faces):
            if face and any(v in chosen_set for v in face) and all(v in depths for v in face) and rng.random() < 0.35:
                plan.remove_faces.append(face_index)

    elif style == "dented":
        if region == "all":
            centres = [vertices[i] for i in rng.sample(ring, min(3, len(ring)))]
            radius = 0.25 * size
            body = [sum(v[k] for v in vertices) / len(vertices) for k in range(3)]
            for index in ring:
                vertex = vertices[index]
                push = 0.0
                for c in centres:
                    distance = math.dist(vertex, c)
                    if distance < radius:
                        push = max(push, (1.0 - distance / radius) ** 2)
                if push > 0:
                    direction = [body[k] - vertex[k] for k in range(3)]
                    norm = math.sqrt(sum(d * d for d in direction)) or 1.0
                    plan.moves[index] = tuple(vertex[k] + direction[k] / norm * strength * size * push for k in range(3))
        else:
            for index, depth in depths.items():
                vertex = vertices[index]
                dx, dy = _normalize(centre1 - vertex[t1], centre2 - vertex[t2])
                smooth = depth * depth * (3 - 2 * depth)             # smoothstep
                moved = list(vertex)
                moved[t1] += dx * strength * size * smooth
                moved[t2] += dy * strength * size * smooth
                plan.moves[index] = tuple(moved)

    else:  # "rough"
        amplitude = strength * size * 0.3
        for index, depth in depths.items():
            vertex = vertices[index]
            plan.moves[index] = tuple(vertex[k] + rng.uniform(-1, 1) * amplitude * depth for k in range(3))

    return plan