import math
import unittest

from blender_ai_agent.tools import mesh_generators as mg


def edge_counts(faces):
    count = {}
    for f in faces:
        for k in range(len(f)):
            e = tuple(sorted((f[k], f[(k + 1) % len(f)])))
            count[e] = count.get(e, 0) + 1
    return count


def watertight(faces):
    return all(c == 2 for c in edge_counts(faces).values())


def volume(vertices, faces):
    total = 0.0
    for f in faces:
        for k in range(1, len(f) - 1):
            a, b, c = vertices[f[0]], vertices[f[k]], vertices[f[k + 1]]
            total += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0]) + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
    return total


def valid(vertices, faces):
    return (all(math.isfinite(c) for v in vertices for c in v)
            and all(0 <= i < len(vertices) for f in faces for i in f) and all(len(set(f)) == len(f) >= 3 for f in faces))


class TestLathe(unittest.TestCase):

    def test_every_preset_is_valid_watertight_and_outward(self):
        for name in mg.PROFILE_PRESETS:
            v, f = mg.lathe_preset(name, 1.0, 0.25, segments=24)
            self.assertTrue(valid(v, f), name)
            self.assertTrue(watertight(f), name)
            self.assertGreater(volume(v, f), 0, name)                           # normals bahar ki taraf

    def test_dimensions_follow_height_and_radius(self):
        v, _ = mg.lathe_preset("vase", height=2.0, radius=0.5)
        self.assertAlmostEqual(max(p[2] for p in v), 2.0)
        self.assertAlmostEqual(min(p[2] for p in v), 0.0, places=6)
        self.assertAlmostEqual(max(math.hypot(p[0], p[1]) for p in v), 0.5, places=6)

    def test_hollow_has_less_volume_than_solid(self):
        solid = mg.lathe_preset("cup", 1.0, 0.3, thickness=0.0, segments=32)
        hollow = mg.lathe_preset("cup", 1.0, 0.3, thickness=0.15, segments=32)
        self.assertLess(volume(*hollow), volume(*solid) * 0.6)
        self.assertGreater(volume(*hollow), 0)

    def test_custom_profile_and_partial_revolve(self):
        v, f = mg.lathe([(0, 0), (0.3, 0), (0.05, 0.1), (0.05, 0.4), (0.3, 0.6)], 16, 360, 0.02)
        self.assertTrue(valid(v, f) and watertight(f))
        pv, pf = mg.lathe([(0.2, 0), (0.2, 1)], 8, 180)
        self.assertEqual(len(pf), 8)
        self.assertTrue(valid(pv, pf))
        self.assertTrue(any(c == 1 for c in edge_counts(pf).values()))        # adha ghumaya => khula

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            mg.lathe([(1, 0)])
        with self.assertRaises(ValueError):
            mg.lathe_preset("spaceship")


class TestTerrain(unittest.TestCase):

    def test_grid_counts_and_all_styles(self):
        for style in mg.TERRAIN_STYLES:
            v, f = mg.terrain(10, 6, 20, 2.0, style=style)
            self.assertEqual(len(v), 21 * 21)
            self.assertEqual(len(f), 400)
            self.assertTrue(valid(v, f), style)
            self.assertAlmostEqual(max(p[0] for p in v), 5.0)
            self.assertAlmostEqual(max(p[1] for p in v), 3.0)
        flat, _ = mg.terrain(style="flat")
        self.assertTrue(all(p[2] == 0 for p in flat))

    def test_height_flat_centre_edge_fade_and_determinism(self):
        v, f = mg.terrain(10, 10, 40, 3.0, seed=2)
        self.assertGreater(max(p[2] for p in v), 0.5)
        self.assertLessEqual(max(p[2] for p in v), 3.0 + 1e-9)
        flat_centre, _ = mg.terrain(10, 10, 40, 3.0, seed=2, flat_radius=0.5)
        centre = [p for p in flat_centre if math.hypot(p[0], p[1]) < 1.0]
        self.assertTrue(all(abs(p[2]) < 0.05 for p in centre))
        faded, _ = mg.terrain(10, 10, 40, 3.0, seed=2, edge_fade=0.4)
        edge = [p for p in faded if abs(p[0]) > 4.9 or abs(p[1]) > 4.9]
        self.assertTrue(all(abs(p[2]) < 1e-9 for p in edge))
        self.assertEqual(mg.terrain(seed=3)[0], mg.terrain(seed=3)[0])
        self.assertNotEqual(mg.terrain(seed=3)[0], mg.terrain(seed=4)[0])

    def test_bad_style(self):
        with self.assertRaises(ValueError):
            mg.terrain(style="lava")


class TestPrism(unittest.TestCase):

    def test_every_kind_extrudes_to_a_closed_solid(self):
        for kind in mg.POLYGON_KINDS:
            pts = mg.polygon_points(kind, sides=8, radius=0.5, width=1.0, depth=1.0)
            self.assertGreaterEqual(len(pts), 3, kind)
            v, f = mg.prism(pts, 0.3)
            self.assertTrue(valid(v, f), kind)
            self.assertTrue(watertight(f), kind)
            self.assertAlmostEqual(max(p[2] for p in v), 0.3)

    def test_gear_star_taper_and_winding(self):
        gear = mg.polygon_points("gear", sides=12, radius=0.5, inner_radius=0.4)
        self.assertEqual(len(gear), 60)
        self.assertAlmostEqual(max(math.hypot(*p) for p in gear), 0.5, places=6)
        star = mg.polygon_points("star", sides=5, radius=0.5, inner_radius=0.2)
        self.assertEqual(len(star), 10)
        v, f = mg.prism(mg.polygon_points("ngon", sides=6), 0.2, taper=0.5)
        top = max(math.hypot(p[0], p[1]) for p in v if p[2] > 0.1)
        bottom = max(math.hypot(p[0], p[1]) for p in v if p[2] < 0.1)
        self.assertAlmostEqual(top, bottom * 0.5, places=6)
        clockwise = list(reversed(mg.polygon_points("ngon", sides=6)))
        self.assertGreater(volume(*mg.prism(clockwise, 0.2)), 0)               # ulta diya to bhi bahar-mukhi

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            mg.prism([(0, 0), (1, 1)], 1)
        with self.assertRaises(ValueError):
            mg.polygon_points("blob")


class TestSdf(unittest.TestCase):

    def test_sphere_volume_watertight_outward(self):
        v, f = mg.sdf_mesh([{"type": "sphere", "radius": 0.5}], resolution=30)
        self.assertTrue(valid(v, f) and watertight(f))
        self.assertAlmostEqual(volume(v, f), 4 / 3 * math.pi * 0.125, delta=0.03)
        radii = [math.sqrt(sum(c * c for c in p)) for p in v]
        self.assertAlmostEqual(sum(radii) / len(radii), 0.5, delta=0.03)

    def test_every_shape_type_produces_a_closed_surface(self):
        shapes = {"sphere": {"radius": 0.4}, "ellipsoid": {"radii": [0.5, 0.3, 0.2]}, "box": {"size": [0.8, 0.6, 0.4], "rounding": 0.1},
                  "capsule": {"a": [0, 0, -0.3], "b": [0, 0, 0.3], "radius": 0.2}, "cylinder": {"radius": 0.3, "height": 0.8},
                  "torus": {"major": 0.4, "minor": 0.12}, "cone": {"radius": 0.4, "height": 0.8}}
        for kind, params in shapes.items():
            v, f = mg.sdf_mesh([dict(params, type=kind)], resolution=32)
            self.assertTrue(f, kind)
            self.assertTrue(valid(v, f), kind)
            self.assertTrue(watertight(f), kind)
            self.assertGreater(volume(v, f), 0, kind)

    def test_boolean_operations(self):
        a = {"type": "box", "size": [1, 1, 1]}
        b = {"type": "sphere", "radius": 0.45, "center": [0.3, 0.3, 0.3]}
        union = volume(*mg.sdf_mesh([a, dict(b, op="union")], 36))
        diff = volume(*mg.sdf_mesh([a, dict(b, op="subtract")], 36))
        inter = volume(*mg.sdf_mesh([a, dict(b, op="intersect")], 36))
        base = volume(*mg.sdf_mesh([a], 36))
        self.assertAlmostEqual(base, 1.0, delta=0.08)
        self.assertGreater(union, base)
        self.assertLess(diff, base)
        self.assertLess(inter, volume(*mg.sdf_mesh([b], 36)) + 0.02)
        self.assertAlmostEqual(union + inter, base + volume(*mg.sdf_mesh([b], 36)), delta=0.12)

    def test_smooth_union_adds_material_in_the_neck(self):
        a = {"type": "sphere", "radius": 0.3, "center": [-0.3, 0, 0]}
        b = {"type": "sphere", "radius": 0.3, "center": [0.3, 0, 0]}
        hard = volume(*mg.sdf_mesh([a, dict(b, op="union")], 36))
        soft = volume(*mg.sdf_mesh([a, dict(b, op="smooth_union", k=0.3)], 36))
        self.assertGreater(soft, hard + 0.003)

    def test_rotation_roughness_bounds_and_determinism(self):
        box = {"type": "box", "size": [1.0, 0.2, 0.2]}
        straight, _ = mg.sdf_mesh([box], 30)
        turned, _ = mg.sdf_mesh([dict(box, rotation=[0, 0, 90])], 30)
        self.assertGreater(max(p[0] for p in straight) - min(p[0] for p in straight), 0.9)
        self.assertGreater(max(p[1] for p in turned) - min(p[1] for p in turned), 0.9)
        self.assertLess(max(p[0] for p in turned) - min(p[0] for p in turned), 0.4)
        rough, _ = mg.sdf_mesh([{"type": "sphere", "radius": 0.5}], 28, roughness=0.06, seed=3)
        radii = [math.sqrt(sum(c * c for c in p)) for p in rough]
        self.assertGreater(max(radii) - min(radii), 0.03)
        self.assertEqual(mg.sdf_mesh([{"type": "sphere"}], 16, roughness=0.05, seed=1)[0], mg.sdf_mesh([{"type": "sphere"}], 16, roughness=0.05, seed=1)[0])
        explicit, _ = mg.sdf_mesh([{"type": "sphere", "radius": 0.3}], 20, bounds=[-1, -1, -1, 1, 1, 1])
        self.assertTrue(explicit)

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            mg.sdf_mesh([], 20)
        with self.assertRaises(ValueError):
            mg.sdf_mesh([{"type": "teapot"}], 20)
        with self.assertRaises(ValueError):
            mg.sdf_mesh([{"type": "sphere"}, {"type": "sphere", "op": "xor"}], 20)


if __name__ == "__main__":
    unittest.main()