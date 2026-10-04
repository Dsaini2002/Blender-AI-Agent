"""
mesh_generators.py
===================
Hinglish: NAYI shapes banane ke general tareeke (pure Python, bpy nahi). Primitives (cube/cone...) se jo na bane:

   lathe   — 2D profile (r, z) ko ghuma kar: bottle, vase, glass, cup, bowl, column, chess piece, lamp, barrel...
   terrain — noise se jameen / pahaad / tila / dunes (campsite ka ground, flat jagah ke saath)
   sdf     — "signed distance" shapes ko jod/ghata kar: rock, cloud, blob, character ka badan, smooth-booleans... (marching surface)
   prism   — 2D polygon (star, gear, ngon, rounded rectangle, cross, arrow, heart) ko extrude: gear, sign, tile, badge...

Har function (vertices, faces) deta hai; bridge.create_mesh unhe Blender object banata hai.
"""

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .mesh_noise import fbm, ridged

Vec = Tuple[float, float, float]
MAX_FACES = 150_000


# =============================================================================
# LATHE
# =============================================================================
# (profile (r, z) 0..1 range mein, default hollow thickness 0..1 radius ke hisaab se)
PROFILE_PRESETS: Dict[str, Tuple[List[Tuple[float, float]], float]] = {
    "bottle": ([(0, 0), (0.88, 0), (1.0, 0.03), (1.0, 0.52), (0.92, 0.60), (0.60, 0.70), (0.34, 0.78), (0.30, 0.90),
                (0.34, 0.94), (0.34, 1.0)], 0.07),
    "vase": ([(0, 0), (0.45, 0), (0.62, 0.04), (1.0, 0.38), (0.88, 0.7), (0.5, 0.84), (0.52, 1.0)], 0.05),
    "wine_glass": ([(0, 0), (0.62, 0), (0.62, 0.03), (0.09, 0.07), (0.09, 0.46), (0.55, 0.56), (0.74, 0.8), (0.74, 1.0)], 0.04),
    "cup": ([(0, 0), (0.7, 0), (0.78, 0.05), (1.0, 0.95), (1.0, 1.0)], 0.06),
    "bowl": ([(0, 0), (0.3, 0.02), (0.65, 0.18), (0.95, 0.55), (1.0, 1.0)], 0.04),
    "column": ([(0, 0), (1.0, 0), (1.0, 0.05), (0.72, 0.08), (0.62, 0.12), (0.62, 0.86), (0.72, 0.9), (0.9, 0.93), (1.0, 0.97), (1.0, 1.0), (0, 1.0)], 0.0),
    "chess_pawn": ([(0, 0), (1.0, 0), (1.0, 0.08), (0.7, 0.14), (0.38, 0.3), (0.26, 0.5), (0.5, 0.56), (0.5, 0.6), (0.32, 0.66),
                    (0.45, 0.78), (0.4, 0.92), (0.18, 1.0), (0, 1.0)], 0.0),
    "lamp": ([(0, 0), (0.6, 0), (0.6, 0.05), (0.14, 0.1), (0.14, 0.55), (0.35, 0.6), (0.95, 0.9), (0.95, 1.0)], 0.03),
    "barrel": ([(0, 0), (0.8, 0), (0.95, 0.2), (1.0, 0.5), (0.95, 0.8), (0.8, 1.0), (0, 1.0)], 0.0),
    "candle": ([(0, 0), (1.0, 0), (1.0, 0.96), (0.8, 1.0), (0, 1.0)], 0.0),
    "bell": ([(0, 0.0), (1.0, 0.0), (0.9, 0.1), (0.62, 0.45), (0.45, 0.8), (0.2, 0.95), (0, 1.0)], 0.05),
    "mug": ([(0, 0), (0.9, 0), (1.0, 0.04), (1.0, 1.0)], 0.07),
}


def lathe(profile: Sequence[Sequence[float]], segments: int = 32, angle_degrees: float = 360.0,
          hollow: float = 0.0) -> Tuple[List[Vec], List[List[int]]]:
    """
    Profile [(r, z), ...] (neeche se upar) ko Z axis ke gird ghumata hai. `hollow` > 0 ho to andar ki deewar banti hai
    (patli deewar wala bartan: khula upar wala sira, `hollow` = deewar ki motaai).
    """
    points = [(max(0.0, float(r)), float(z)) for r, z in profile]
    if len(points) < 2:
        raise ValueError("lathe needs at least 2 profile points [r, z]")
    segments = max(3, min(256, int(segments)))
    if hollow > 0:
        z0 = points[0][1]
        inner = []
        for r, z in reversed(points):
            inner.append((max(r - hollow, 0.0), z + (hollow if abs(z - z0) < 1e-9 else 0.0)))
        points = points + inner

    full = abs(angle_degrees) >= 359.999
    angle = math.radians(angle_degrees)
    columns = segments if full else segments + 1
    eps = 1e-9

    vertices: List[Vec] = []
    rings: List[List[int]] = []                       # har profile point ke vertex indices
    for r, z in points:
        if r < eps:
            vertices.append((0.0, 0.0, z))
            rings.append([len(vertices) - 1] * columns)
        else:
            ring = []
            for k in range(columns):
                theta = angle * k / segments
                vertices.append((r * math.cos(theta), r * math.sin(theta), z))
                ring.append(len(vertices) - 1)
            rings.append(ring)

    faces: List[List[int]] = []
    span = segments if not full else segments
    for a_index in range(len(points) - 1):
        ra, rb = points[a_index][0], points[a_index + 1][0]
        a_ring, b_ring = rings[a_index], rings[a_index + 1]
        if ra < eps and rb < eps:
            continue
        for k in range(span):
            k2 = (k + 1) % columns if full else k + 1
            if ra < eps:
                faces.append([a_ring[0], b_ring[k2], b_ring[k]])
            elif rb < eps:
                faces.append([a_ring[k], a_ring[k2], b_ring[0]])
            else:
                faces.append([a_ring[k], a_ring[k2], b_ring[k2], b_ring[k]])
    return vertices, faces


def lathe_preset(name: str, height: float = 1.0, radius: float = 0.25, thickness: Optional[float] = None,
                 segments: int = 32) -> Tuple[List[Vec], List[List[int]]]:
    key = str(name).strip().lower().replace(" ", "_")
    if key not in PROFILE_PRESETS:
        raise ValueError(f"unknown lathe preset '{name}'. Presets: {', '.join(sorted(PROFILE_PRESETS))}")
    profile, default_hollow = PROFILE_PRESETS[key]
    scaled = [(r * radius, z * height) for r, z in profile]
    hollow = (default_hollow if thickness is None else thickness) * radius
    return lathe(scaled, segments, 360.0, hollow)


# =============================================================================
# TERRAIN
# =============================================================================
TERRAIN_STYLES = ("hills", "mountains", "dunes", "plateau", "flat")


def terrain(size_x: float = 10.0, size_y: float = 10.0, resolution: int = 40, height: float = 1.5, noise_scale: float = 3.0,
            octaves: int = 4, seed: int = 1, style: str = "hills", flat_radius: float = 0.0,
            edge_fade: float = 0.0) -> Tuple[List[Vec], List[List[int]]]:
    """
    Z-up jameen ka grid (origin center mein). `flat_radius` (0..1, size ka hissa): beech mein samtal jagah (campfire/tent ke liye).
    `edge_fade` (0..1): kinaare dheere-dheere samtal.
    """
    if style not in TERRAIN_STYLES:
        raise ValueError(f"terrain style must be one of {list(TERRAIN_STYLES)}")
    resolution = max(4, min(220, int(resolution)))
    frequency = noise_scale / max(size_x, size_y, 1e-6)
    vertices: List[Vec] = []
    for j in range(resolution + 1):
        for i in range(resolution + 1):
            x = (i / resolution - 0.5) * size_x
            y = (j / resolution - 0.5) * size_y
            n = fbm(x * frequency, y * frequency, 0.0, octaves, seed=seed)         # [-1, 1]
            n01 = 0.5 + 0.5 * n
            if style == "flat":
                z = 0.0
            elif style == "hills":
                z = n01 * height
            elif style == "mountains":
                z = (0.5 + 0.5 * ridged(x * frequency, y * frequency, 0.0, octaves, seed=seed)) ** 1.6 * height * 1.6
            elif style == "dunes":
                z = height * (0.5 + 0.5 * math.sin(x * frequency * math.pi + n * 2.2)) * (0.6 + 0.4 * n01)
            else:  # plateau
                t = max(0.0, min(1.0, (n01 - 0.42) / 0.16))
                z = height * t * t * (3 - 2 * t)
            r = math.hypot(x / (size_x / 2), y / (size_y / 2)) / math.sqrt(2)                    # 0 center, ~1 kona
            if flat_radius > 0:
                t = max(0.0, min(1.0, (r - flat_radius * 0.5) / max(flat_radius * 0.5, 1e-6)))
                z *= t * t * (3 - 2 * t)
            if edge_fade > 0:
                e = min(i, resolution - i, j, resolution - j) / (resolution * 0.5)               # 0 kinara .. 1 center
                t = max(0.0, min(1.0, e / edge_fade))
                z *= t * t * (3 - 2 * t)
            vertices.append((x, y, z))
    faces = [[j * (resolution + 1) + i, j * (resolution + 1) + i + 1, (j + 1) * (resolution + 1) + i + 1,
              (j + 1) * (resolution + 1) + i] for j in range(resolution) for i in range(resolution)]
    return vertices, faces


# =============================================================================
# PRISM (polygon extrude)
# =============================================================================
POLYGON_KINDS = ("ngon", "star", "gear", "rounded_rect", "cross", "arrow", "heart")


def polygon_points(kind: str, sides: int = 6, radius: float = 0.5, inner_radius: float = 0.0, width: float = 1.0,
                   depth: float = 1.0, corner: float = 0.15, segments: int = 6) -> List[Tuple[float, float]]:
    """2D polygon (counter-clockwise)."""
    sides = max(3, min(64, int(sides)))
    if kind == "ngon":
        return [(radius * math.cos(2 * math.pi * k / sides), radius * math.sin(2 * math.pi * k / sides)) for k in range(sides)]
    if kind == "star":
        inner = inner_radius or radius * 0.45
        points = []
        for k in range(sides * 2):
            r = radius if k % 2 == 0 else inner
            a = math.pi * k / sides + math.pi / 2
            points.append((r * math.cos(a), r * math.sin(a)))
        return points
    if kind == "gear":
        inner = inner_radius or radius * 0.8
        points = []
        for k in range(sides):
            base = 2 * math.pi * k / sides
            step = 2 * math.pi / sides
            for fraction, r in ((0.0, inner), (0.18, inner), (0.3, radius), (0.7, radius), (0.82, inner)):
                a = base + step * fraction
                points.append((r * math.cos(a), r * math.sin(a)))
        return points
    if kind == "rounded_rect":
        hw, hd = width / 2, depth / 2
        c = max(1e-6, min(corner, hw, hd))
        segments = max(1, int(segments))
        points = []
        for cx, cy, start in ((hw - c, hd - c, 0), (-hw + c, hd - c, 90), (-hw + c, -hd + c, 180), (hw - c, -hd + c, 270)):
            for s in range(segments + 1):
                a = math.radians(start + 90 * s / segments)
                points.append((cx + c * math.cos(a), cy + c * math.sin(a)))
        return points
    if kind == "cross":
        a, b = width / 2, max(1e-6, (inner_radius or width * 0.3)) / 2
        return [(b, a), (-b, a), (-b, b), (-a, b), (-a, -b), (-b, -b), (-b, -a), (b, -a), (b, -b), (a, -b), (a, b), (b, b)]
    if kind == "arrow":
        w, h = width / 2, depth / 2
        return [(0, h), (w, 0), (w * 0.35, 0), (w * 0.35, -h), (-w * 0.35, -h), (-w * 0.35, 0), (-w, 0)]
    if kind == "heart":
        points = []
        for k in range(48):
            t = 2 * math.pi * k / 48
            x = 16 * math.sin(t) ** 3
            y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
            points.append((x / 34.0 * width, y / 34.0 * depth))
        return points
    raise ValueError(f"polygon kind must be one of {list(POLYGON_KINDS)}")


def prism(polygon: Sequence[Sequence[float]], height: float = 0.2, taper: float = 1.0,
          cap: bool = True) -> Tuple[List[Vec], List[List[int]]]:
    """2D polygon ko upar ki taraf extrude karta hai. taper < 1: upar ka sira chhota (frustum), > 1: bada."""
    pts = [(float(p[0]), float(p[1])) for p in polygon]
    if len(pts) < 3:
        raise ValueError("a polygon needs at least 3 points")
    # CCW pakka karo
    area = sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1] for k in range(len(pts)))
    if area < 0:
        pts.reverse()
    n = len(pts)
    cx = sum(p[0] for p in pts) / n
    cy = sum(p[1] for p in pts) / n
    vertices: List[Vec] = [(x, y, 0.0) for x, y in pts]
    vertices += [(cx + (x - cx) * taper, cy + (y - cy) * taper, height) for x, y in pts]
    faces = [[k, (k + 1) % n, n + (k + 1) % n, n + k] for k in range(n)]
    if cap:
        faces.append(list(reversed(range(n))))                 # neeche (normal neeche)
        faces.append([n + k for k in range(n)])                # upar
    return vertices, faces


# =============================================================================
# SDF  (signed distance fields) + surface nets
# =============================================================================
SDF_TYPES = ("sphere", "ellipsoid", "box", "capsule", "cylinder", "torus", "cone", "round_cone", "plane")
SDF_OPS = ("union", "subtract", "intersect", "smooth_union")


def _rot_inverse(rotation_degrees: Sequence[float]):
    """XYZ euler (degrees) ka ulta rotation function: p -> p (object ke local frame mein)."""
    rx, ry, rz = (math.radians(a) for a in rotation_degrees)
    if abs(rx) + abs(ry) + abs(rz) < 1e-12:
        return None
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)

    def inverse(p):
        x, y, z = p
        # R = Rz * Ry * Rx  =>  R^-1 = Rx^-1 * Ry^-1 * Rz^-1
        x, y = x * cz + y * sz, -x * sz + y * cz
        x, z = x * cy - z * sy, x * sy + z * cy
        y, z = y * cx + z * sx, -y * sx + z * cx
        return (x, y, z)

    return inverse


def _make_sdf(shape: Dict[str, Any]):
    kind = str(shape.get("type", "sphere")).lower()
    if kind not in SDF_TYPES:
        raise ValueError(f"sdf shape type must be one of {list(SDF_TYPES)}, got '{kind}'")
    cx, cy, cz = (float(c) for c in shape.get("center", [0, 0, 0]))
    inverse = _rot_inverse(shape.get("rotation", [0, 0, 0]))
    rounding = float(shape.get("rounding", 0.0))

    def local(p):
        q = (p[0] - cx, p[1] - cy, p[2] - cz)
        return inverse(q) if inverse else q

    if kind == "sphere":
        r = float(shape.get("radius", 0.5))
        return lambda p: math.sqrt(sum(c * c for c in local(p))) - r
    if kind == "ellipsoid":
        radii = [max(1e-6, float(c)) for c in shape.get("radii", [0.5, 0.5, 0.5])]

        def ellipsoid(p):
            q = local(p)
            k0 = math.sqrt(sum((q[i] / radii[i]) ** 2 for i in range(3)))
            k1 = math.sqrt(sum((q[i] / (radii[i] * radii[i])) ** 2 for i in range(3)))
            return k0 * (k0 - 1.0) / k1 if k1 > 1e-12 else -min(radii)
        return ellipsoid
    if kind == "box":
        half = [float(c) / 2 for c in shape.get("size", [1, 1, 1])]

        def box(p):
            q = local(p)
            d = [abs(q[i]) - half[i] + rounding for i in range(3)]
            outside = math.sqrt(sum(max(c, 0.0) ** 2 for c in d))
            return outside + min(max(d), 0.0) - rounding
        return box
    if kind == "capsule":
        a = [float(c) for c in shape.get("a", [0, 0, -0.5])]
        b = [float(c) for c in shape.get("b", [0, 0, 0.5])]
        r = float(shape.get("radius", 0.2))
        ab = [b[i] - a[i] for i in range(3)]
        denom = sum(c * c for c in ab) or 1e-12

        def capsule(p):
            ap = [p[i] - a[i] for i in range(3)]
            t = max(0.0, min(1.0, sum(ap[i] * ab[i] for i in range(3)) / denom))
            return math.sqrt(sum((ap[i] - ab[i] * t) ** 2 for i in range(3))) - r
        return capsule
    if kind == "cylinder":
        r, h = float(shape.get("radius", 0.3)), float(shape.get("height", 1.0)) / 2

        def cylinder(p):
            q = local(p)
            dx, dz = math.hypot(q[0], q[1]) - r + rounding, abs(q[2]) - h + rounding
            return min(max(dx, dz), 0.0) + math.hypot(max(dx, 0.0), max(dz, 0.0)) - rounding
        return cylinder
    if kind == "torus":
        major, minor = float(shape.get("major", 0.5)), float(shape.get("minor", 0.15))

        def torus(p):
            q = local(p)
            return math.hypot(math.hypot(q[0], q[1]) - major, q[2]) - minor
        return torus
    if kind == "cone":
        # Sapaat sire wala cone / frustum: neeche radius `radius`, upar `radius_top` (default 0 = nok), `height` oonchai.
        r1, r2, h = float(shape.get("radius", 0.5)), float(shape.get("radius_top", 0.0)), max(float(shape.get("height", 1.0)), 1e-6)
        hh = h / 2.0
        k1x, k1y, k2x, k2y = r2, hh, r2 - r1, 2.0 * hh
        k2_dot = k2x * k2x + k2y * k2y

        def capped_cone(p):
            q = local(p)
            qr, qy = math.hypot(q[0], q[1]), q[2] - hh
            cax = qr - min(qr, r1 if qy < 0.0 else r2)
            cay = abs(qy) - hh
            t = max(0.0, min(1.0, ((k1x - qr) * k2x + (k1y - qy) * k2y) / k2_dot))
            cbx, cby = qr - k1x + k2x * t, qy - k1y + k2y * t
            sign = -1.0 if (cbx < 0.0 and cay < 0.0) else 1.0
            return sign * math.sqrt(min(cax * cax + cay * cay, cbx * cbx + cby * cby))
        return capped_cone
    if kind == "round_cone":
        r1, r2, h = float(shape.get("radius", 0.5)), float(shape.get("radius_top", 0.0)), float(shape.get("height", 1.0))
        b = (r1 - r2) / max(h, 1e-9)
        a = math.sqrt(max(0.0, 1.0 - b * b))

        def round_cone(p):
            q = local(p)
            qr, qz = math.hypot(q[0], q[1]), q[2]
            k = qr * (-b) + qz * a
            if k < 0.0:
                return math.hypot(qr, qz) - r1
            if k > a * h:
                return math.hypot(qr, qz - h) - r2
            return qr * a + qz * b - r1
        return round_cone
    # plane: z <= center.z andar
    return lambda p: p[2] - cz


def _combine(a: float, b: float, op: str, k: float) -> float:
    if op == "subtract":
        return max(a, -b)
    if op == "intersect":
        return max(a, b)
    if op == "smooth_union" and k > 1e-9:
        h = max(k - abs(a - b), 0.0) / k
        return min(a, b) - h * h * k * 0.25
    return min(a, b)


def _shape_extent(shape: Dict[str, Any]) -> float:
    """Shape ka center se kitna bahar tak jaa sakta hai (bounds nikalne ke liye, thoda zyada)."""
    kind = str(shape.get("type", "sphere")).lower()
    c = shape.get("center", [0, 0, 0])
    if kind == "sphere":
        return float(shape.get("radius", 0.5))
    if kind == "ellipsoid":
        return max(float(v) for v in shape.get("radii", [0.5, 0.5, 0.5]))
    if kind == "box":
        return math.sqrt(sum((float(v) / 2) ** 2 for v in shape.get("size", [1, 1, 1])))
    if kind == "capsule":
        pts = [shape.get("a", [0, 0, -0.5]), shape.get("b", [0, 0, 0.5])]
        return max(math.sqrt(sum((float(p[i]) - float(c[i])) ** 2 for i in range(3))) for p in pts) + float(shape.get("radius", 0.2))
    if kind == "cylinder":
        return math.hypot(float(shape.get("radius", 0.3)), float(shape.get("height", 1.0)) / 2)
    if kind == "torus":
        return float(shape.get("major", 0.5)) + float(shape.get("minor", 0.15))
    if kind in ("cone", "round_cone"):
        return math.hypot(max(float(shape.get("radius", 0.5)), float(shape.get("radius_top", 0.0))), float(shape.get("height", 1.0)))
    return 1.0


def sdf_function(shapes: Sequence[Dict[str, Any]], roughness: float = 0.0, noise_scale: float = 4.0, seed: int = 1):
    """Shapes ki list -> ek distance function d(p). Pehli shape ka `op` ignore hota hai."""
    if not shapes:
        raise ValueError("sdf needs at least one shape")
    parts = [(_make_sdf(s), str(s.get("op", "union")).lower(), float(s.get("k", 0.15))) for s in shapes]
    for _, op, _ in parts:
        if op not in SDF_OPS:
            raise ValueError(f"sdf op must be one of {list(SDF_OPS)}, got '{op}'")

    def distance(p):
        d = parts[0][0](p)
        for fn, op, k in parts[1:]:
            d = _combine(d, fn(p), op, k)
        if roughness:
            d += roughness * fbm(p[0] * noise_scale, p[1] * noise_scale, p[2] * noise_scale, 3, seed=seed)
        return d

    return distance


def surface_nets(distance, mins: Sequence[float], maxs: Sequence[float], resolution: int) -> Tuple[List[Vec], List[List[int]]]:
    """Naive surface nets: distance field (0 = satah) se quad mesh. `resolution` = sabse lambe axis par voxels."""
    extent = [maxs[i] - mins[i] for i in range(3)]
    cell = max(extent) / max(4, int(resolution))
    dims = [int(math.ceil(extent[i] / cell)) + 1 for i in range(3)]
    nx, ny, nz = dims

    values = [0.0] * (nx * ny * nz)
    def gi(i, j, k): return (k * ny + j) * nx + i
    for k in range(nz):
        z = mins[2] + k * cell
        for j in range(ny):
            y = mins[1] + j * cell
            base = (k * ny + j) * nx
            for i in range(nx):
                values[base + i] = distance((mins[0] + i * cell, y, z))

    corner_offsets = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    cube_edges = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
    vertices: List[Vec] = []
    cell_vertex: Dict[Tuple[int, int, int], int] = {}

    for k in range(nz - 1):
        for j in range(ny - 1):
            for i in range(nx - 1):
                cv = [values[gi(i + o[0], j + o[1], k + o[2])] for o in corner_offsets]
                negative = sum(1 for v in cv if v < 0)
                if negative == 0 or negative == 8:
                    continue
                sx = sy = sz = 0.0
                count = 0
                for a, b in cube_edges:
                    va, vb = cv[a], cv[b]
                    if (va < 0) != (vb < 0):
                        t = va / (va - vb)
                        oa, ob = corner_offsets[a], corner_offsets[b]
                        sx += oa[0] + (ob[0] - oa[0]) * t
                        sy += oa[1] + (ob[1] - oa[1]) * t
                        sz += oa[2] + (ob[2] - oa[2]) * t
                        count += 1
                cell_vertex[(i, j, k)] = len(vertices)
                vertices.append((mins[0] + (i + sx / count) * cell, mins[1] + (j + sy / count) * cell, mins[2] + (k + sz / count) * cell))

    faces: List[List[int]] = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                here = values[gi(i, j, k)]
                # x-edge
                if i + 1 < nx and j >= 1 and k >= 1 and j < ny and k < nz:
                    there = values[gi(i + 1, j, k)]
                    if (here < 0) != (there < 0):
                        quad = [cell_vertex.get((i, j - 1, k - 1)), cell_vertex.get((i, j, k - 1)),
                                cell_vertex.get((i, j, k)), cell_vertex.get((i, j - 1, k))]
                        if None not in quad:
                            faces.append(quad if here < 0 else quad[::-1])
                # y-edge
                if j + 1 < ny and i >= 1 and k >= 1:
                    there = values[gi(i, j + 1, k)]
                    if (here < 0) != (there < 0):
                        quad = [cell_vertex.get((i - 1, j, k - 1)), cell_vertex.get((i, j, k - 1)),
                                cell_vertex.get((i, j, k)), cell_vertex.get((i - 1, j, k))]
                        if None not in quad:
                            faces.append(quad[::-1] if here < 0 else quad)
                # z-edge
                if k + 1 < nz and i >= 1 and j >= 1:
                    there = values[gi(i, j, k + 1)]
                    if (here < 0) != (there < 0):
                        quad = [cell_vertex.get((i - 1, j - 1, k)), cell_vertex.get((i, j - 1, k)),
                                cell_vertex.get((i, j, k)), cell_vertex.get((i - 1, j, k))]
                        if None not in quad:
                            faces.append(quad if here < 0 else quad[::-1])
    if len(faces) > MAX_FACES:
        raise ValueError(f"sdf result has {len(faces)} faces (max {MAX_FACES}); lower the resolution")
    return weld_vertices(vertices, faces, cell * 1e-4)


def weld_vertices(vertices: Sequence[Vec], faces: Sequence[Sequence[int]], tolerance: float) -> Tuple[List[Vec], List[List[int]]]:
    """
    Ek hi jagah par baithe vertices ko jod deta hai aur zero-area (degenerate) faces hata deta hai.
    Surface nets mein jab satah bilkul grid point se guzarti hai (jaise symmetric sphere) to do cell-vertices ek hi position
    par aa jaate hain; Blender ka QuadriFlow aise mesh ko "non-manifold" kehkar ruk jaata tha.
    """
    inv = 1.0 / max(tolerance, 1e-12)
    key_to_index: Dict[Tuple[int, int, int], int] = {}
    remap: List[int] = []
    welded: List[Vec] = []
    for v in vertices:
        key = (round(v[0] * inv), round(v[1] * inv), round(v[2] * inv))
        index = key_to_index.get(key)
        if index is None:
            index = len(welded)
            key_to_index[key] = index
            welded.append(v)
        remap.append(index)
    cleaned: List[List[int]] = []
    for face in faces:
        loop: List[int] = []
        for i in face:
            j = remap[i]
            if not loop or loop[-1] != j:
                loop.append(j)
        if len(loop) > 1 and loop[0] == loop[-1]:
            loop.pop()
        if len(loop) >= 3 and len(set(loop)) == len(loop):
            cleaned.append(loop)
    if len(welded) == len(vertices) and len(cleaned) == len(faces):
        return list(vertices), [list(f) for f in faces]
    used = sorted({i for f in cleaned for i in f})
    new_index = {old: new for new, old in enumerate(used)}
    return [welded[i] for i in used], [[new_index[i] for i in f] for f in cleaned]


def sdf_mesh(shapes: Sequence[Dict[str, Any]], resolution: int = 40, bounds: Optional[Sequence[float]] = None,
             roughness: float = 0.0, noise_scale: float = 4.0, seed: int = 1, margin: float = 0.1) -> Tuple[List[Vec], List[List[int]]]:
    """Shapes (union / subtract / intersect / smooth_union) se mesh. `bounds` = [minx, miny, minz, maxx, maxy, maxz] (warna khud)."""
    resolution = max(8, min(90, int(resolution)))
    distance = sdf_function(shapes, roughness, noise_scale, seed)
    if bounds:
        lo, hi = [float(v) for v in bounds[:3]], [float(v) for v in bounds[3:6]]
    else:
        lo, hi = [1e9] * 3, [-1e9] * 3
        for s in shapes:
            e = _shape_extent(s) + float(s.get("k", 0.0)) * 0.5 + abs(roughness) * 1.5
            if str(s.get("op", "union")).lower() == "subtract" and s is not shapes[0]:
                continue                                     # ghatane wali shape se bounds nahi badhte
            c = [float(v) for v in s.get("center", [0, 0, 0])]
            if str(s.get("type", "sphere")).lower() == "capsule":
                c = [0.0, 0.0, 0.0] if "center" not in s else c
            for k in range(3):
                lo[k], hi[k] = min(lo[k], c[k] - e), max(hi[k], c[k] + e)
        lo = [v - margin for v in lo]
        hi = [v + margin for v in hi]
    if any(hi[i] - lo[i] <= 1e-6 for i in range(3)):
        raise ValueError("sdf bounds are empty")
    return surface_nets(distance, lo, hi, resolution)