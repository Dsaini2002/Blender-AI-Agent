import math
import unittest

from blender_ai_agent.tools.mesh_damage import DamagePlan, REGIONS, STYLES, plan_damage, region_vertex_indices


def bottle(segments=16, rings=12, radius=0.4, height=3.0):
    """Ek simple 'bottle': khada cylinder, Z upar."""
    verts = [(radius * math.cos(2 * math.pi * s / segments), radius * math.sin(2 * math.pi * s / segments),
              height * r / (rings - 1)) for r in range(rings) for s in range(segments)]
    faces = [[r * segments + s, r * segments + (s + 1) % segments, (r + 1) * segments + (s + 1) % segments,
              (r + 1) * segments + s] for r in range(rings - 1) for s in range(segments)]
    return verts, faces


def apply(verts, plan):
    return [plan.moves.get(i, v) for i, v in enumerate(verts)]


class TestRegions(unittest.TestCase):

    def test_top_region_is_the_top_quarter_with_depth_towards_the_rim(self):
        verts, _ = bottle()
        region = region_vertex_indices(verts, "top", 0.25)
        self.assertTrue(region)
        self.assertTrue(all(verts[i][2] >= 3.0 * 0.75 - 1e-9 for i in region))
        self.assertEqual(max(region.values()), 1.0)                       # sabse upar wale vertices depth 1.0
        top_ring = [i for i, v in enumerate(verts) if v[2] == 3.0]
        self.assertTrue(all(region[i] == 1.0 for i in top_ring))

    def test_every_named_region_picks_the_right_side(self):
        verts, _ = bottle()
        for name, axis, comparison in (("bottom", 2, min), ("left", 0, min), ("right", 0, max),
                                       ("front", 1, min), ("back", 1, max)):
            region = region_vertex_indices(verts, name, 0.2)
            self.assertTrue(region, name)
            edge = comparison(v[axis] for v in verts)
            self.assertTrue(any(abs(verts[i][axis] - edge) < 1e-9 for i in region), name)

    def test_all_covers_everything_and_flat_meshes_do_not_crash(self):
        verts, _ = bottle()
        self.assertEqual(len(region_vertex_indices(verts, "all", 0.1)), len(verts))
        flat = [(0, 0, 0), (1, 0, 0), (1, 1, 0)]
        self.assertEqual(len(region_vertex_indices(flat, "top", 0.2)), 3)
        self.assertEqual(region_vertex_indices([], "top"), {})

    def test_portion_controls_how_much_is_affected(self):
        verts, _ = bottle()
        small = len(region_vertex_indices(verts, "top", 0.1))
        big = len(region_vertex_indices(verts, "top", 0.5))
        self.assertLess(small, big)


class TestBroken(unittest.TestCase):
    """'The top of the bottle should look a little broken.'"""

    def test_top_rim_is_lowered_unevenly_and_nothing_below_the_region_moves(self):
        verts, faces = bottle()
        plan = plan_damage(verts, faces, "top", 0.2, 0.15, "broken", seed=3)
        region = region_vertex_indices(verts, "top", 0.2)
        self.assertEqual(set(plan.moves), set(region))                    # sirf region ke vertices hile
        after = apply(verts, plan)
        for i in range(len(verts)):
            if i not in region:
                self.assertEqual(after[i], verts[i])                      # baaki bottle bilkul wahi
        top_ring = [i for i, v in enumerate(verts) if v[2] == 3.0]
        drops = [verts[i][2] - after[i][2] for i in top_ring]
        self.assertTrue(all(d >= -1e-9 for d in drops))                   # kinara neeche gaya, upar nahi
        self.assertGreater(max(drops) - min(drops), 0.05)                 # aur barabar nahi — kaante / notches
        self.assertLess(max(a[2] for a in after), 3.0)                    # ab sabse upar ka point pehle se neecha

    def test_some_faces_are_removed_only_inside_the_region(self):
        verts, faces = bottle(segments=24, rings=20)
        plan = plan_damage(verts, faces, "top", 0.25, 0.2, "broken", seed=5)
        region = region_vertex_indices(verts, "top", 0.25)
        self.assertGreater(len(plan.remove_faces), 0)
        for face_index in plan.remove_faces:
            self.assertTrue(all(v in region for v in faces[face_index]))
        self.assertLess(len(plan.remove_faces), len(faces) * 0.2)         # poori bottle gayab nahi

    def test_strength_scales_the_damage(self):
        verts, faces = bottle()
        def worst_drop(strength):
            plan = plan_damage(verts, faces, "top", 0.2, strength, "broken", seed=1)
            after = apply(verts, plan)
            return max(verts[i][2] - after[i][2] for i in plan.moves)
        self.assertLess(worst_drop(0.05), worst_drop(0.3))

    def test_same_seed_same_result_different_seed_different_break(self):
        verts, faces = bottle()
        one = plan_damage(verts, faces, "top", 0.2, 0.15, "broken", seed=1)
        again = plan_damage(verts, faces, "top", 0.2, 0.15, "broken", seed=1)
        other = plan_damage(verts, faces, "top", 0.2, 0.15, "broken", seed=2)
        self.assertEqual(one.moves, again.moves)
        self.assertEqual(one.remove_faces, again.remove_faces)
        self.assertNotEqual(one.moves, other.moves)

    def test_bottom_region_breaks_the_bottom_upwards(self):
        verts, faces = bottle()
        plan = plan_damage(verts, faces, "bottom", 0.2, 0.2, "broken", seed=1)
        after = apply(verts, plan)
        bottom_ring = [i for i, v in enumerate(verts) if v[2] == 0.0]
        self.assertTrue(all(after[i][2] >= verts[i][2] - 1e-9 for i in bottom_ring))      # neeche wala kinara upar utha
        self.assertGreater(max(after[i][2] - verts[i][2] for i in bottom_ring), 0.01)


class TestOtherStyles(unittest.TestCase):

    def test_chipped_touches_only_a_few_vertices(self):
        verts, faces = bottle()
        plan = plan_damage(verts, faces, "top", 0.3, 0.2, "chipped", seed=1)
        region = region_vertex_indices(verts, "top", 0.3)
        self.assertTrue(0 < len(plan.moves) < len(region) * 0.5)

    def test_dented_pushes_vertices_towards_the_axis(self):
        verts, faces = bottle()
        plan = plan_damage(verts, faces, "top", 0.3, 0.2, "dented", seed=1)
        after = apply(verts, plan)
        radius = lambda v: math.hypot(v[0], v[1])
        moved = [i for i in plan.moves if radius(after[i]) < radius(verts[i]) - 1e-9]
        self.assertTrue(moved)
        self.assertTrue(all(radius(after[i]) <= radius(verts[i]) + 1e-9 for i in plan.moves))   # kuch bahar nahi gaya
        self.assertEqual(plan.remove_faces, [])

    def test_dent_on_the_whole_object(self):
        verts, faces = bottle()
        plan = plan_damage(verts, faces, "all", 1.0, 0.2, "dented", seed=2)
        self.assertTrue(plan.moves)

    def test_rough_moves_every_region_vertex_a_little(self):
        verts, faces = bottle()
        plan = plan_damage(verts, faces, "top", 0.2, 0.1, "rough", seed=1)
        region = region_vertex_indices(verts, "top", 0.2)
        self.assertEqual(set(plan.moves), set(region))
        biggest = max(math.dist(verts[i], plan.moves[i]) for i in plan.moves)
        self.assertLess(biggest, 0.1 * 3.0 * 0.3 * 1.8 + 1e-9)            # strength*size*0.3 * sqrt(3) se zyada nahi

    def test_every_style_and_region_combination_runs(self):
        verts, faces = bottle(segments=8, rings=6)
        for style in STYLES:
            for region in REGIONS:
                plan = plan_damage(verts, faces, region, 0.3, 0.2, style, seed=4)
                self.assertIsInstance(plan, DamagePlan)
                self.assertTrue(all(0 <= i < len(verts) for i in plan.moves))
                self.assertTrue(all(0 <= f < len(faces) for f in plan.remove_faces))
                for position in plan.moves.values():
                    self.assertTrue(all(math.isfinite(c) for c in position))


class TestEdgeCases(unittest.TestCase):

    def test_empty_and_tiny_meshes(self):
        self.assertEqual(plan_damage([], [], "top").moves, {})
        tri = [(0, 0, 0), (1, 0, 0), (0, 1, 1)]
        for style in STYLES:
            plan = plan_damage(tri, [[0, 1, 2]], "top", 0.5, 0.3, style, seed=1)
            self.assertTrue(all(math.isfinite(c) for p in plan.moves.values() for c in p))

    def test_out_of_range_strength_is_clamped_not_crashing(self):
        verts, faces = bottle()
        plan = plan_damage(verts, faces, "top", 5.0, 99.0, "broken", seed=1)
        self.assertTrue(plan.moves)
        self.assertTrue(all(math.isfinite(c) for p in plan.moves.values() for c in p))

    def test_unknown_region_falls_back_to_the_whole_mesh(self):
        verts, faces = bottle(segments=8, rings=6)
        self.assertEqual(plan_damage(verts, faces, "sideways", 0.3, 0.2, "rough").affected, len(verts))


if __name__ == "__main__":
    unittest.main()