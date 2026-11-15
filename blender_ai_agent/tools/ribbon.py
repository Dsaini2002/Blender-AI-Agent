"""Flat ribbon meshes for paths, roads and sidewalks.

A round curve bevel turns a "2 m wide path" into a 2 m tall tube. These helpers turn
the same centre-line points into a thin, flat slab of the right width that lies on the
ground, with mitred corners so the width stays even around bends.
"""

import math
from typing import List, Sequence, Tuple

Vec3 = Tuple[float, float, float]


def smooth_points(points: Sequence[Sequence[float]], closed: bool = False, samples: int = 6) -> List[Vec3]:
    """Catmull-Rom curve through the points (passes through every point), `samples` steps per segment."""
    pts = [tuple(float(c) for c in p[:3]) for p in points]
    n = len(pts)
    if n < 3 or samples <= 1:
        return pts + ([pts[0]] if closed and n > 2 else [])

    def at(i):
        if closed:
            return pts[i % n]
        return pts[max(0, min(n - 1, i))]

    out: List[Vec3] = []
    segments = n if closed else n - 1
    for i in range(segments):
        p0, p1, p2, p3 = at(i - 1), at(i), at(i + 1), at(i + 2)
        for s in range(samples):
            t = s / samples
            t2, t3 = t * t, t * t * t
            out.append(tuple(
                0.5 * (2 * p1[k] + (-p0[k] + p2[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                       + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3)
                for k in range(3)))
    out.append(pts[0] if closed else pts[-1])
    return out


def _unit2(x: float, y: float):
    length = math.hypot(x, y)
    if length < 1e-9:
        return None
    return x / length, y / length


def ribbon_mesh(path: Sequence[Sequence[float]], width: float, depth: float = 0.02,
                closed: bool = False, base_index: int = 0):
    """Vertices and quad faces of a flat slab following `path` in XY.

    Top face sits `depth` above each path point and the bottom `depth` below it, so a
    path drawn at z=0.02 on a ground plane shows cleanly without z-fighting."""
    pts = [tuple(float(c) for c in p[:3]) for p in path]
    # drop consecutive duplicates (zero-length segments have no direction)
    cleaned: List[Vec3] = []
    for p in pts:
        if not cleaned or math.dist(p[:2], cleaned[-1][:2]) > 1e-6:
            cleaned.append(p)
    if closed and len(cleaned) > 2 and math.dist(cleaned[0][:2], cleaned[-1][:2]) < 1e-6:
        cleaned.pop()
    pts = cleaned
    n = len(pts)
    if n < 2:
        return [], []

    half = width / 2.0
    verts: List[Vec3] = []
    for i, p in enumerate(pts):
        if closed:
            prev, nxt = pts[(i - 1) % n], pts[(i + 1) % n]
        else:
            prev, nxt = pts[max(0, i - 1)], pts[min(n - 1, i + 1)]
        d_in = _unit2(p[0] - prev[0], p[1] - prev[1]) if prev is not p else None
        d_out = _unit2(nxt[0] - p[0], nxt[1] - p[1]) if nxt is not p else None
        d_in = d_in or d_out
        d_out = d_out or d_in
        tangent = _unit2(d_in[0] + d_out[0], d_in[1] + d_out[1]) or d_in
        nx, ny = -tangent[1], tangent[0]
        # mitre: keep the width even through bends (capped so hairpins don't spike)
        cos_half = abs(nx * -d_in[1] + ny * d_in[0])
        scale = 1.0 / max(cos_half, 0.5)
        ox, oy = nx * half * scale, ny * half * scale
        x, y, z = p
        verts.extend([
            (x + ox, y + oy, z + depth),   # left top
            (x - ox, y - oy, z + depth),   # right top
            (x + ox, y + oy, z - depth),   # left bottom
            (x - ox, y - oy, z - depth),   # right bottom
        ])

    faces = []
    b = base_index
    pairs = [(i, i + 1) for i in range(n - 1)] + ([(n - 1, 0)] if closed else [])
    for i, j in pairs:
        lt_i, rt_i, lb_i, rb_i = (b + 4 * i + k for k in range(4))
        lt_j, rt_j, lb_j, rb_j = (b + 4 * j + k for k in range(4))
        faces.append((lt_i, rt_i, rt_j, lt_j))   # top (faces up)
        faces.append((lb_j, rb_j, rb_i, lb_i))   # bottom
        faces.append((lb_i, lt_i, lt_j, lb_j))   # left side
        faces.append((rb_j, rt_j, rt_i, rb_i))   # right side
    if not closed:
        faces.append((b + 0, b + 2, b + 3, b + 1))                       # start cap
        e = b + 4 * (n - 1)
        faces.append((e + 1, e + 3, e + 2, e + 0))                       # end cap
    return verts, faces


def has_sharp_corner(points, closed: bool = False, limit_degrees: float = 50.0) -> bool:
    """True when the line turns by `limit_degrees` or more somewhere (a box, an L) - those corners stay sharp."""
    pts = [tuple(float(c) for c in p[:2]) for p in points]
    n = len(pts)
    idx = range(n) if closed else range(1, n - 1)
    for i in idx:
        a, b, c = pts[(i - 1) % n], pts[i], pts[(i + 1) % n]
        u = _unit2(b[0] - a[0], b[1] - a[1])
        w = _unit2(c[0] - b[0], c[1] - b[1])
        if u is None or w is None:
            continue
        cos_turn = max(-1.0, min(1.0, u[0] * w[0] + u[1] * w[1]))
        if math.degrees(math.acos(cos_turn)) >= limit_degrees:
            return True
    return False


def centre_line(stroke, closed: bool = False, smooth: bool = True, samples: int = 6):
    """The line a ribbon follows: smoothed through the points, unless smoothing is off or it has sharp corners."""
    if smooth and not has_sharp_corner(stroke, closed):
        return smooth_points(stroke, closed, samples)
    line = [tuple(p[:3]) for p in stroke]
    return line + ([line[0]] if closed and line and line[0] != line[-1] else [])


def strokes_mesh(strokes, width: float, depth: float = 0.02, closed: bool = False,
                 smooth: bool = True, samples: int = 6):
    """One mesh from several centre-lines (an X, a T junction, a network of paths)."""
    all_verts: List[Vec3] = []
    all_faces = []
    for index, stroke in enumerate(strokes):
        path = centre_line(stroke, closed, smooth, samples)
        # lift each later stroke a hair so crossings (the middle of an X) don't flicker
        lift = 0.002 * index
        path = [(p[0], p[1], p[2] + lift) for p in path]
        verts, faces = ribbon_mesh(path, width, depth, closed, base_index=len(all_verts))
        all_verts.extend(verts)
        all_faces.extend(faces)
    return all_verts, all_faces
