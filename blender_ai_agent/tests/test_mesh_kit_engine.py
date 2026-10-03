import math
import unittest

from blender_ai_agent.tools import mesh_engine as me
from blender_ai_agent.tools.mesh_noise import fbm, rand01, ridged, value_noise


def bottle(segments=20, rings=14, radius=0.4, height=3.0):
    verts = [(radius * math.cos(2 * math.pi * s / segments), radius * math.sin(2 * math.pi * s / segments),
              height * r / (rings - 1)) for r in range(rings) for s in range(segments)]
    faces = [[r * segments + s, r * segments + (s + 1) % segments, (r + 1) * segments + (s + 1) % segments,
              (r + 1) * segments + s] for r in range(rings - 1) for s in range(segments)]
    return verts, faces


def cube(n=1):
    """Band cube (6 quads) — topology tests ke liye."""
    v = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
    f = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return v, f


def edges_manifold(faces):
    count = {}
    for f in faces:
        for k in range(len(f)):
            e = tuple(sorted((f[k], f[(k + 1) % len(f)])))
            count[e] = count.get(e, 0) + 1
    return count


def finite(verts):
    return all(math.isfinite(c) for v in verts for c in v)


def apply(verts, result):
    return [result.moves.get(i, v) for i, v in enumerate(verts)]


def run(op, verts, faces):
    info = me.analyze(verts, faces)
    return me.run_vertex_op(op, info, 1)


class TestNoise(unittest.TestCase):

    def test_ranges_determinism_and_seed(self):
        for i in range(300):
            assert -1.0 <= value_noise(i * 0.31, i * 0.17, i * 0.07, 3) <= 1.0
            assert -1.0 <= fbm(i * 0.2, 1.1, 2.2, 4, seed=1) <= 1.0
            assert -1.0 <= ridged(i * 0.2, 1.1, 2.2, 3) <= 1.0
            assert 0.0 <= rand01(i, 5) < 1.0
        self.assertEqual(value_noise(1.5, 2.5, 3.5, 4), value_noise(1.5, 2.5, 3.5, 4))
        self.assertNotEqual(value_noise(1.5, 2.5, 3.5, 4), value_noise(1.5, 2.5, 3.5, 5))


class TestSelection(unittest.TestCase):

    def setUp(self):
        self.verts, self.faces = bottle()
        self.info = me.analyze(self.verts, self.faces)

    def weights(self, sel):
        return me.selection_weights(sel, self.info, 1)

    def test_all_none_and_names(self):
        n = len(self.verts)
        self.assertEqual(self.weights(None), [1.0] * n)
        self.assertEqual(self.weights("all"), [1.0] * n)
        top = self.weights("top")
        self.assertGreater(sum(1 for w in top if w > 0), 0)
        self.assertTrue(all(self.verts[i][2] >= 2.2 for i, w in enumerate(top) if w > 0))
        for alias in ("neck", "lid", "rim", "upper"):
            self.assertEqual(self.weights(alias), top, alias)
        self.assertEqual(self.weights("base"), self.weights("bottom"))

    def test_falloff_modes(self):
        smooth = self.weights({"region": "top", "portion": 0.3, "falloff": "smooth"})
        none = self.weights({"region": "top", "portion": 0.3, "falloff": "none"})
        self.assertTrue(set(none) <= {0.0, 1.0})
        self.assertGreater(max(smooth), 0.99)
        self.assertTrue(any(0 < w < 1 for w in smooth))

    def test_sphere_box_slab(self):
        sphere = self.weights({"sphere": {"center": [0.5, 0.5, 0.5], "radius": 0.2}})
        mid = [i for i, v in enumerate(self.verts) if abs(v[2] - 1.5) < 0.2]
        self.assertTrue(any(sphere[i] > 0 for i in mid))
        self.assertEqual(sphere[0], 0.0)                                   # neeche ka kinara bahar
        box = self.weights({"box": {"min": [0, 0, 0.8], "max": [1, 1, 1]}})
        self.assertTrue(all(self.verts[i][2] >= 0.8 * 3.0 - 1e-9 for i, w in enumerate(box) if w > 0))
        slab = self.weights({"slab": {"axis": "z", "from": 0.4, "to": 0.6}})
        self.assertTrue(all(1.2 - 1e-9 <= self.verts[i][2] <= 1.8 + 1e-9 for i, w in enumerate(slab) if w > 0))

    def test_noise_random_facing(self):
        patches = self.weights({"noise": {"scale": 3, "threshold": 0.5}})
        self.assertTrue(0 < sum(1 for w in patches if w > 0.5) < len(patches))
        rnd = self.weights({"random": {"fraction": 0.25, "seed": 4}})
        self.assertAlmostEqual(sum(rnd) / len(rnd), 0.25, delta=0.1)
        self.assertEqual(rnd, self.weights({"random": {"fraction": 0.25, "seed": 4}}))
        sides = self.weights({"facing": {"direction": "right", "tolerance": 0.5}})
        self.assertTrue(all(self.verts[i][0] > 0 for i, w in enumerate(sides) if w > 0))

    def test_combinators_invert_strength(self):
        top, bottom = self.weights("top"), self.weights("bottom")
        either = self.weights({"or": ["top", "bottom"]})
        self.assertTrue(all(abs(either[i] - max(top[i], bottom[i])) < 1e-9 for i in range(len(top))))
        both = self.weights({"and": ["top", "bottom"]})
        self.assertEqual(sum(both), 0.0)
        self.assertEqual(self.weights({"not": "top"}), [1.0 - w for w in top])
        self.assertEqual(self.weights({"region": "top", "invert": True}), [1.0 - w for w in top])
        half = self.weights({"region": "top", "strength": 0.5})
        self.assertTrue(all(abs(half[i] - top[i] * 0.5) < 1e-9 for i in range(len(top))))

    def test_bad_selectors_raise_clearly(self):
        for bad in ({"wobble": 1}, {"region": "sideways"}, 42):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.weights(bad)


class TestVertexOperators(unittest.TestCase):

    def setUp(self):
        self.verts, self.faces = bottle()

    def test_move_scale_rotate(self):
        moved = apply(self.verts, run({"op": "move", "offset": [0.1, 0, 0], "select": "top"}, self.verts, self.faces))
        self.assertTrue(any(abs(m[0] - v[0] - 0.1 * 3.0) < 1e-9 for m, v in zip(moved, self.verts)))
        scaled = apply(self.verts, run({"op": "scale", "factor": 2.0, "pivot": "center"}, self.verts, self.faces))
        self.assertAlmostEqual(max(v[0] for v in scaled), 2 * max(v[0] for v in self.verts), places=6)
        rotated = apply(self.verts, run({"op": "rotate", "angle": 90, "axis": "z"}, self.verts, self.faces))
        self.assertAlmostEqual(math.hypot(rotated[3][0], rotated[3][1]), math.hypot(self.verts[3][0], self.verts[3][1]), places=9)
        self.assertNotAlmostEqual(rotated[3][0], self.verts[3][0], places=3)

    def test_twist_rotates_more_towards_the_top_and_keeps_the_axis(self):
        out = apply(self.verts, run({"op": "twist", "angle": 180, "centered": False}, self.verts, self.faces))
        bottom = [i for i, v in enumerate(self.verts) if v[2] == 0.0]
        top = [i for i, v in enumerate(self.verts) if v[2] == 3.0]
        self.assertTrue(all(abs(out[i][0] - self.verts[i][0]) < 1e-9 for i in bottom))      # t=0: koi ghumav nahi
        self.assertTrue(all(abs(out[i][0] + self.verts[i][0]) < 1e-6 for i in top))          # t=1: 180 degree
        self.assertTrue(all(abs(out[i][2] - self.verts[i][2]) < 1e-9 for i in range(len(out))))
        self.assertTrue(all(abs(math.hypot(out[i][0], out[i][1]) - math.hypot(*self.verts[i][:2])) < 1e-9 for i in range(len(out))))

    def test_bend_curves_the_axis_and_roughly_keeps_length(self):
        out = apply(self.verts, run({"op": "bend", "angle": 60, "axis": "z", "direction": "x"}, self.verts, self.faces))
        top_before = max(v[2] for v in self.verts)
        top_after = max(v[2] for v in out)
        self.assertLess(top_after, top_before)                                                # jhukne se top neeche
        self.assertGreater(max(v[0] for v in out), max(v[0] for v in self.verts) + 0.3)       # aur bagal mein gaya
        self.assertTrue(finite(out))

    def test_taper_stretch_bulge_inflate(self):
        tapered = apply(self.verts, run({"op": "taper", "axis": "z", "start": 1.0, "end": 0.2}, self.verts, self.faces))
        self.assertAlmostEqual(max(math.hypot(v[0], v[1]) for v in tapered if v[2] > 2.99), 0.4 * 0.2, places=6)
        stretched = apply(self.verts, run({"op": "stretch", "axis": "z", "factor": 2.0, "pivot": "base"}, self.verts, self.faces))
        self.assertAlmostEqual(max(v[2] for v in stretched), 6.0, places=6)
        kept = apply(self.verts, run({"op": "stretch", "axis": "z", "factor": 4.0, "pivot": "base", "preserve_volume": True}, self.verts, self.faces))
        self.assertAlmostEqual(max(v[0] for v in kept), 0.4 / 2.0, places=6)                  # width 1/sqrt(4)
        bulged = apply(self.verts, run({"op": "bulge", "amount": 0.5}, self.verts, self.faces))
        self.assertGreater(max(math.hypot(v[0], v[1]) for v in bulged), 0.4 * 1.45)
        inflated = apply(self.verts, run({"op": "inflate", "amount": 0.05}, self.verts, self.faces))
        self.assertGreater(max(math.hypot(v[0], v[1]) for v in inflated), 0.4 + 0.05 * 3.0 * 0.9)

    def test_noise_is_bounded_and_deterministic(self):
        op = {"op": "noise", "amplitude": 0.05, "scale": 5, "seed": 3}
        a = run(op, self.verts, self.faces)
        b = run(op, self.verts, self.faces)
        self.assertEqual(a.moves, b.moves)
        worst = max(math.dist(self.verts[i], p) for i, p in a.moves.items())
        self.assertLessEqual(worst, 0.05 * 3.0 + 1e-9)
        self.assertNotEqual(a.moves, run(dict(op, seed=4), self.verts, self.faces).moves)
        xyz = run({"op": "noise", "mode": "xyz", "amplitude": 0.02}, self.verts, self.faces)
        self.assertTrue(xyz.moves)

    def test_wave_is_a_sine(self):
        out = apply(self.verts, run({"op": "wave", "amplitude": 0.05, "wavelength": 0.5, "axis": "z", "displace": "x"}, self.verts, self.faces))
        for i in (0, 25, 100, 200):
            expected = 0.05 * 3.0 * math.sin(2 * math.pi * (self.verts[i][2] - 0.0) / (0.5 * 3.0))
            self.assertAlmostEqual(out[i][0] - self.verts[i][0], expected, places=9)

    def test_melt_lowers_the_top_widens_the_bottom_and_never_goes_below_the_base(self):
        out = apply(self.verts, run({"op": "melt", "amount": 0.6, "spread": 1.0}, self.verts, self.faces))
        self.assertLess(max(v[2] for v in out), 3.0 - 0.3)
        self.assertGreaterEqual(min(v[2] for v in out), 0.0 - 1e-9)
        bottom_radius = max(math.hypot(v[0], v[1]) for v, o in zip(self.verts, out) if v[2] < 0.1)
        self.assertGreater(max(math.hypot(o[0], o[1]) for v, o in zip(self.verts, out) if v[2] < 0.1), bottom_radius)

    def test_spikes_pull_vertices_outwards_along_the_normal(self):
        result = run({"op": "spikes", "count": 5, "length": 0.2, "radius": 0.15, "seed": 2}, self.verts, self.faces)
        self.assertTrue(result.moves)
        info = me.analyze(self.verts, self.faces)
        for i, p in result.moves.items():
            outward = sum((p[k] - self.verts[i][k]) * info.normals[i][k] for k in range(3))
            self.assertGreater(outward, 0)

    def test_smooth_reduces_roughness(self):
        rough = apply(self.verts, run({"op": "noise", "amplitude": 0.1, "scale": 12, "mode": "xyz"}, self.verts, self.faces))
        info_before = me.analyze(rough, self.faces)
        smoothed = apply(rough, me.run_vertex_op({"op": "smooth", "iterations": 5, "factor": 0.8}, info_before, 1))
        def roughness(vs):
            adj = me.analyze(vs, self.faces).adjacency()
            return sum(math.dist(vs[i], [sum(vs[n][k] for n in adj[i]) / len(adj[i]) for k in range(3)]) for i in range(len(vs)) if adj[i])
        self.assertLess(roughness(smoothed), roughness(rough) * 0.8)

    def test_crack_digs_a_groove_into_the_surface(self):
        result = run({"op": "crack", "count": 2, "depth": 0.08, "width": 0.05, "length": 0.8, "seed": 1}, self.verts, self.faces)
        info = me.analyze(self.verts, self.faces)
        self.assertTrue(result.moves)
        inward = sum(1 for i, p in result.moves.items()
                     if sum((p[k] - self.verts[i][k]) * info.normals[i][k] for k in range(3)) < 0)
        self.assertGreater(inward, len(result.moves) * 0.5)

    def test_selection_limits_every_operator(self):
        for op in ({"op": "noise", "amplitude": 0.05}, {"op": "inflate", "amount": 0.05}, {"op": "scale", "factor": 1.5},
                   {"op": "wave", "amplitude": 0.05}, {"op": "twist", "angle": 90}):
            result = run(dict(op, select="top"), self.verts, self.faces)
            weights = me.selection_weights("top", me.analyze(self.verts, self.faces))
            self.assertTrue(all(weights[i] > 0 for i in result.moves), op["op"])

    def test_every_operator_returns_finite_values_on_edge_case_meshes(self):
        flat = ([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [[0, 1, 2, 3]])
        for verts, faces in (flat, cube(), bottle(6, 4)):
            for name in me.VERTEX_OPS:
                result = run({"op": name}, verts, faces)
                self.assertTrue(finite(list(result.moves.values())), name)
                self.assertTrue(all(0 <= f < len(faces) for f in result.remove_faces), name)


class TestFaceRemoval(unittest.TestCase):

    def test_holes_remove_clusters_inside_the_selection(self):
        verts, faces = bottle(24, 20)
        result = run({"op": "holes", "count": 4, "radius": 0.2, "select": "top", "seed": 2}, verts, faces)
        weights = me.selection_weights("top", me.analyze(verts, faces))
        self.assertGreater(len(result.remove_faces), 4)
        self.assertTrue(all(sum(weights[v] for v in faces[f]) / 4 > 0.5 for f in result.remove_faces))
        frac = run({"op": "holes", "fraction": 0.3}, verts, faces)
        self.assertAlmostEqual(len(frac.remove_faces) / len(faces), 0.3, delta=0.08)

    def test_erode_and_damage(self):
        verts, faces = bottle(24, 20)
        eroded = run({"op": "erode", "threshold": 0.55}, verts, faces)
        self.assertGreater(len(eroded.remove_faces), 0)
        self.assertLess(len(eroded.remove_faces), len(faces))
        broken = run({"op": "damage", "style": "broken", "region": "top", "strength": 0.2}, verts, faces)
        self.assertGreater(len(broken.moves), 0)


class TestTopology(unittest.TestCase):

    def test_subdivide_everything_quadruples_quads_and_stays_closed(self):
        verts, faces = cube()
        result = me.apply_topology({"op": "subdivide", "levels": 1}, verts, faces)
        self.assertEqual(len(result.faces), 24)
        self.assertEqual(len(result.face_source), 24)
        self.assertTrue(all(c == 2 for c in edges_manifold(result.faces).values()))
        two = me.apply_topology({"op": "subdivide", "levels": 2}, verts, faces)
        self.assertEqual(len(two.faces), 96)

    def test_subdivide_a_selection_leaves_no_cracks(self):
        verts, faces = bottle(16, 10)
        result = me.apply_topology({"op": "subdivide", "levels": 1, "select": "top"}, verts, faces)
        self.assertGreater(len(result.faces), len(faces))
        # bottle khula hai (upar/neeche ring); koi bhi khula kinara sirf unhi do ring par ho => beech mein T-junction / daraar nahi
        open_edges = [e for e, c in edges_manifold(result.faces).items() if c == 1]
        self.assertTrue(open_edges)
        for a, b in open_edges:
            self.assertTrue(all(abs(result.vertices[i][2] - z) < 1e-9 for i in (a, b) for z in [result.vertices[a][2]]))
            self.assertTrue(result.vertices[a][2] in (0.0, 3.0) and result.vertices[b][2] in (0.0, 3.0))
        self.assertTrue(all(c <= 2 for c in edges_manifold(result.faces).values()))

    def test_cut_keeps_one_side_adds_a_cap_and_stays_closed(self):
        verts, faces = cube()
        result = me.apply_topology({"op": "cut", "axis": "z", "at": 0.5, "keep": "below", "cap": True}, verts, faces)
        self.assertAlmostEqual(max(v[2] for v in result.vertices), 0.5)
        self.assertAlmostEqual(min(v[2] for v in result.vertices), 0.0)
        self.assertTrue(all(c == 2 for c in edges_manifold(result.faces).values()))
        self.assertIn(-1, result.face_source)                                               # cap = naya face
        above = me.apply_topology({"op": "cut", "axis": "z", "at": 0.25, "keep": "above"}, verts, faces)
        self.assertAlmostEqual(min(v[2] for v in above.vertices), 0.25)

    def test_cut_without_cap_is_open_and_cut_on_a_round_mesh_works(self):
        verts, faces = bottle(16, 10)
        open_cut = me.apply_topology({"op": "cut", "axis": "z", "at": 0.5, "cap": False}, verts, faces)
        self.assertNotIn(-1, open_cut.face_source)
        capped = me.apply_topology({"op": "cut", "axis": "z", "at": 0.5, "cap": True}, verts, faces)
        self.assertIn(-1, capped.face_source)
        self.assertTrue(finite(capped.vertices))
        with self.assertRaises(ValueError):
            me.apply_topology({"op": "cut", "axis": "z", "value": -5.0, "keep": "above", "cap": False}, *cube()) \
                if False else me.apply_topology({"op": "cut", "axis": "z", "value": -5.0, "keep": "below"}, *cube())

    def test_extrude_pushes_selected_faces_out_with_side_walls(self):
        verts, faces = cube()
        result = me.apply_topology({"op": "extrude", "amount": 0.5, "select": "top"}, verts, faces)
        self.assertGreater(max(v[2] for v in result.vertices), 1.4)
        self.assertGreater(len(result.faces), len(faces))

    def test_shatter_makes_separate_pieces(self):
        verts, faces = bottle(20, 14)
        result = me.apply_topology({"op": "shatter", "pieces": 8, "spread": 0.3, "seed": 2}, verts, faces)
        self.assertEqual(len(result.faces), len(faces))
        self.assertGreater(len(result.vertices), len(verts))                                  # vertices duplicate hue
        manifold = edges_manifold(result.faces)
        self.assertTrue(any(c == 1 for c in manifold.values()))                               # ab kinaare khule hain
        self.assertTrue(finite(result.vertices))


class TestPresetsAndPipeline(unittest.TestCase):

    def test_every_preset_runs_on_several_meshes(self):
        for verts, faces in (bottle(), bottle(8, 5), cube()):
            for name in me.PRESET_NAMES:
                result = me.apply_ops(verts, faces, [{"op": "preset", "name": name, "strength": 0.6}])
                self.assertTrue(finite(result.vertices), name)
                self.assertTrue(all(0 <= i < len(result.vertices) for f in result.faces for i in f), name)
                self.assertEqual(len(result.faces), len(result.face_source), name)

    def test_synonyms_and_hinglish(self):
        for word, expected in (("pighla hua", "melted"), ("toota", "broken"), ("kaante wala", "spiky"), ("rusty", "eroded"),
                               ("puffy", "inflated"), ("cut in half", "sliced"), ("Twisted", "twisted"), ("rotten", "eroded"),
                               ("chhed", "holey"), ("mudaa", "bent")):
            self.assertEqual(me.resolve_preset_name(word), expected, word)
        self.assertIsNone(me.resolve_preset_name("explodingunicorn"))
        with self.assertRaises(ValueError):
            me.expand_preset("explodingunicorn")

    def test_strength_scales_the_effect(self):
        verts, faces = bottle()
        weak = me.apply_ops(verts, faces, [{"op": "preset", "name": "twisted", "strength": 0.1, "detail": 0}])
        strong = me.apply_ops(verts, faces, [{"op": "preset", "name": "twisted", "strength": 1.0, "detail": 0}])
        shift = lambda r: max(math.dist(a, b) for a, b in zip(verts, r.vertices))
        self.assertLess(shift(weak), shift(strong))

    def test_low_poly_gets_extra_detail_but_dense_meshes_do_not(self):
        verts, faces = cube()
        low = me.expand_preset("melted", 0.5, face_count=6)
        self.assertEqual(low[0]["op"], "subdivide")
        dense = me.expand_preset("melted", 0.5, face_count=50000)
        self.assertNotEqual(dense[0]["op"], "subdivide")
        forced = me.expand_preset("melted", 0.5, detail=2, face_count=50000)
        self.assertEqual(forced[0]["levels"], 2)
        self.assertEqual(me.expand_preset("melted", 0.5, detail=0, face_count=6)[0]["op"], "melt")

    def test_pipeline_runs_in_order_and_tracks_sources(self):
        verts, faces = bottle(16, 10)
        result = me.apply_ops(verts, faces, [
            {"op": "subdivide", "levels": 1, "select": "top"},
            {"op": "wave", "amplitude": 0.03, "wavelength": 0.1, "axis": "x", "displace": "z", "select": "top"},
            {"op": "holes", "count": 3, "radius": 0.1, "select": "top", "seed": 1},
        ])
        self.assertTrue(result.topology_changed)
        self.assertEqual(len(result.notes), 3)
        self.assertTrue(all(0 <= s < len(faces) for s in result.face_source if s >= 0))

    def test_vertex_only_pipeline_reports_removed_faces_for_the_bridge(self):
        verts, faces = bottle(24, 20)
        result = me.apply_ops(verts, faces, [{"op": "holes", "fraction": 0.2}])
        self.assertFalse(result.topology_changed)
        self.assertEqual(len(result.vertices), len(verts))
        self.assertEqual(len(result.removed_faces), len(faces) - len(result.faces))
        self.assertTrue(result.removed_faces)

    def test_same_seed_same_result(self):
        verts, faces = bottle()
        ops = [{"op": "preset", "name": "cracked", "strength": 0.7, "seed": 5}]
        a, b = me.apply_ops(verts, faces, ops, 5), me.apply_ops(verts, faces, ops, 5)
        self.assertEqual(a.vertices, b.vertices)
        self.assertEqual(a.faces, b.faces)

    def test_oversized_results_are_stopped_with_a_note_not_run(self):
        verts, faces = bottle(120, 120)
        result = me.apply_ops(verts, faces, [{"op": "subdivide", "levels": 3}, {"op": "subdivide", "levels": 3}])
        self.assertLessEqual(len(result.faces), me.MAX_FACES)
        self.assertTrue(any("stopped" in note for note in result.notes))

    def test_input_is_never_modified(self):
        verts, faces = bottle()
        copy_v, copy_f = [tuple(v) for v in verts], [list(f) for f in faces]
        me.apply_ops(verts, faces, [{"op": "preset", "name": "melted"}, {"op": "holes", "fraction": 0.2}])
        self.assertEqual(verts, copy_v)
        self.assertEqual(faces, copy_f)


class TestValidation(unittest.TestCase):

    def test_good_ops_pass(self):
        ops = me.validate_ops([{"op": "twist", "angle": 90, "select": "top"}, {"op": "preset", "name": "pighla hua"},
                               {"op": "holes", "select": {"and": ["top", {"noise": {"scale": 3}}]}}])
        self.assertEqual(len(ops), 3)

    def test_bad_ops_have_helpful_messages(self):
        for bad, text in (([], "non-empty"), ("twist", "non-empty"), ([{"angle": 4}], "'op' key"), ([{"op": "wobble"}], "unknown operator"),
                          ([{"op": "preset", "name": "zzz"}], "unknown preset"), ([{"op": "move", "select": "sideways"}], "select"),
                          ([{"op": "script", "code": "import os"}], "script"), ([5], "object")):
            with self.assertRaises(ValueError, msg=str(bad)) as ctx:
                me.validate_ops(bad)
            self.assertIn(text, str(ctx.exception), str(bad))

    def test_too_many_operators(self):
        with self.assertRaises(ValueError):
            me.validate_ops([{"op": "smooth"}] * 41)


class TestParameterNormalisation(unittest.TestCase):

    def test_xyz_dicts_numeric_strings_and_vector_strings(self):
        out = me.normalize_params({"op": "move", "offset": {"x": "0.1", "Y": 0, "z": 0}, "angle": "90", "pivot": "0.5, 0.5, 0",
                                   "factor": ["2", "1", "1"], "select": {"sphere": {"center": {"x": 0.5, "y": 0.5, "z": 1}, "radius": "0.2"}}})
        self.assertEqual(out["offset"], [0.1, 0, 0])
        self.assertEqual(out["angle"], 90.0)
        self.assertEqual(out["pivot"], [0.5, 0.5, 0.0])
        self.assertEqual(out["factor"], [2.0, 1.0, 1.0])
        self.assertEqual(out["select"]["sphere"]["center"], [0.5, 0.5, 1])
        self.assertEqual(out["select"]["sphere"]["radius"], 0.2)

    def test_text_values_are_never_converted(self):
        out = me.normalize_params({"op": "twist", "axis": "z", "region": "top", "code": "dz = 1", "pivot": "base", "style": "broken",
                                   "direction": "up", "mode": "normal"})
        self.assertEqual(out, {"op": "twist", "axis": "z", "region": "top", "code": "dz = 1", "pivot": "base", "style": "broken",
                               "direction": "up", "mode": "normal"})
        self.assertEqual(me.normalize_params({"angle": "nan", "x": 1}), {"angle": "nan", "x": 1})

    def test_ops_with_llm_formats_actually_run(self):
        verts, faces = bottle()
        result = me.apply_ops(verts, faces, [
            {"op": "move", "offset": {"x": 0.1, "y": 0, "z": 0}, "select": "top"},
            {"op": "twist", "angle": "45"},
            {"op": "inflate", "amount": "0.02", "select": {"sphere": {"center": {"x": 0.5, "y": 0.5, "z": 0.5}, "radius": "0.3"}}}])
        self.assertTrue(finite(result.vertices))
        self.assertGreater(max(v[0] for v in result.vertices), 0.4)


if __name__ == "__main__":
    unittest.main()