"""Regressions from the "create a park" run (log 20261114_134101):

- material.assign called with object= / material= instead of object_name= / material_name=,
  and the recovery then guessed a random object ('path_plaza');
- imported benches at scale 0.01 "fixed" to 1.0, turning 2 m benches into 200 m walls;
- a "2 m wide path" built as a 2 m thick round tube, with the X's two lines joined end-to-end;
- no grass recipe, so the lawn got dark-brown dirt.
"""

from . import _bpy_stub  # noqa: F401

import math
import unittest

from blender_ai_agent.agent.models import ToolCall
from blender_ai_agent.agent.scene_checks import geometry_problems
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.reliability.errors import ErrorCode, ToolError
from blender_ai_agent.reliability.recovery import RecoveryManager
from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tests.fakes_ext import FakeBridge
from blender_ai_agent.tools import shader_nodes as sn
from blender_ai_agent.tools.curve_tools import CreateCurveTool
from blender_ai_agent.tools.material_tools import AssignMaterialTool
from blender_ai_agent.tools.object_tools import TransformObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.ribbon import ribbon_mesh, smooth_points, strokes_mesh
from blender_ai_agent.tools.scene_tools import SceneInspectTool


class ScaledBridge(FakeBridge):
    """measure_objects that respects scale and mesh vertices, like real Blender."""

    def measure_objects(self, names):
        lo, hi, found = [1e9] * 3, [-1e9] * 3, False
        for name in names:
            o = self.get_object(name)
            if o is None:
                continue
            verts = getattr(o, "fake_vertices", None)
            if verts:
                pts = [[v[k] * o.scale[k] + o.location[k] for k in range(3)] for v in verts]
            else:
                box = getattr(o, "fake_bbox", None) or {"min": [-0.5, -0.5, 0.0], "max": [0.5, 0.5, 1.0]}
                pts = [[box[c][k] * o.scale[k] + o.location[k] for k in range(3)] for c in ("min", "max")]
            for p in pts:
                for k in range(3):
                    lo[k], hi[k] = min(lo[k], p[k]), max(hi[k], p[k])
            found = True
        return {"min": lo, "max": hi} if found else None

    def create_mesh(self, name, vertices, faces, location=None, rotation=None, scale=None, shade_smooth=False):
        obj = super().create_mesh(name, vertices, faces, location=location, rotation=rotation, scale=scale,
                                  shade_smooth=shade_smooth)
        obj.fake_vertices = [list(v) for v in vertices]
        obj.fake_faces = [list(f) for f in faces]
        return obj


class TestArgumentAliases(unittest.TestCase):

    def setUp(self):
        self.bridge = FakeBridge(objects=[FakeObject(name="park_lamp_1_bulb"), FakeObject(name="path_plaza")])
        self.bridge.create_material("lamp_emission_mat")
        self.tool = AssignMaterialTool(self.bridge)

    def test_object_and_material_keys_are_understood(self):
        result = self.tool.execute({"object": "park_lamp_1_bulb", "material": "lamp_emission_mat"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(self.bridge.get_object("park_lamp_1_bulb").material_name, "lamp_emission_mat")
        self.assertIsNone(self.bridge.get_object("path_plaza").material_name)

    def test_unknown_keys_are_named_in_the_error(self):
        result = self.tool.execute({"thing": "park_lamp_1_bulb"})
        self.assertFalse(result.success)
        self.assertIn("Valid arguments: object_name, material_name", result.error)
        self.assertIn("Ignored unknown arguments: thing", result.error)

    def test_real_key_wins_over_alias(self):
        result = self.tool.execute({"object": "path_plaza", "object_name": "park_lamp_1_bulb",
                                    "material_name": "lamp_emission_mat"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(self.bridge.get_object("park_lamp_1_bulb").material_name, "lamp_emission_mat")
        self.assertIsNone(self.bridge.get_object("path_plaza").material_name)


class TestRecoveryDoesNotGuessTheWrongObject(unittest.TestCase):

    def _recovery(self, bridge):
        registry = ToolRegistry()
        registry.register(AssignMaterialTool(bridge))
        registry.register(TransformObjectTool(bridge))
        registry.register(SceneInspectTool(SceneInspector(bridge)))
        return RecoveryManager(ToolCaller(registry))

    def test_named_target_under_unknown_key_is_used(self):
        bridge = FakeBridge(objects=[FakeObject(name="park_lamp_1_bulb"), FakeObject(name="path_plaza")])
        call = ToolCall(tool_name="material.assign", arguments={"thing": "park_lamp_1_bulb", "material_name": "m"})
        error = ToolError(code=ErrorCode.MISSING_ARGUMENT, message="missing 'object_name'", recoverable=True)
        fixed = self._recovery(bridge).attempt_recovery(call, error)
        self.assertEqual(fixed.arguments["object_name"], "park_lamp_1_bulb")

    def test_unknown_string_target_means_no_guess(self):
        bridge = FakeBridge(objects=[FakeObject(name="path_plaza")])
        call = ToolCall(tool_name="material.assign", arguments={"thing": "lamp_that_does_not_exist", "material_name": "m"})
        error = ToolError(code=ErrorCode.MISSING_ARGUMENT, message="missing 'object_name'", recoverable=True)
        self.assertIsNone(self._recovery(bridge).attempt_recovery(call, error))


class TestOversizedScale(unittest.TestCase):

    def test_import_scale_fixed_to_one_is_refused(self):
        bench = FakeObject(name="Bench_01", scale=[0.01, 0.01, 0.01])
        bench.fake_bbox = {"min": [-98.6, -38.6, 0.0], "max": [98.6, 38.6, 55.0]}      # 1.97 x 0.77 x 0.55 m at 0.01
        bridge = ScaledBridge(objects=[bench])
        result = TransformObjectTool(bridge).execute({"name": "Bench_01", "scale": [1, 1, 1]})
        self.assertFalse(result.success)
        self.assertIn("100x bigger", result.error)
        self.assertEqual(list(bench.scale), [0.01, 0.01, 0.01])

    def test_rotation_only_and_normal_scaling_still_work(self):
        cube = FakeObject(name="crate")
        bridge = ScaledBridge(objects=[cube])
        tool = TransformObjectTool(bridge)
        self.assertTrue(tool.execute({"name": "crate", "rotation": [0, 0, 1.0]}).success)
        self.assertTrue(tool.execute({"name": "crate", "scale": [3, 3, 3]}).success)

    def test_big_flat_ground_is_allowed(self):
        ground = FakeObject(name="ground")
        ground.fake_bbox = {"min": [-1, -1, 0], "max": [1, 1, 0.0]}
        bridge = ScaledBridge(objects=[ground])
        result = TransformObjectTool(bridge).execute({"name": "ground", "scale": [60, 60, 1]})
        self.assertTrue(result.success, result.error)

    def test_geometry_check_flags_a_giant_bench(self):
        bench = FakeObject(name="Bench_01.002")
        bench.fake_bbox = {"min": [-98, -38, 0.0], "max": [98, 38, 55.0]}
        bench.material_name = "wood"
        problems = geometry_problems(FakeBridge(objects=[bench]), ["Bench_01.002"])
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["severity"], "high")
        self.assertIn("scaled up by mistake", problems[0]["issue"])
        self.assertIn("object.transform(name='Bench_01.002'", problems[0]["fix"])

    def test_normal_sized_things_are_not_flagged(self):
        tree = FakeObject(name="park_tree_1_trunk")
        tree.fake_bbox = {"min": [-0.3, -0.3, 0.0], "max": [0.3, 0.3, 8.0]}
        tree.material_name = "bark"
        self.assertEqual(geometry_problems(FakeBridge(objects=[tree]), ["park_tree_1_trunk"]), [])


class TestRibbon(unittest.TestCase):

    def test_straight_ribbon_has_the_right_width_and_faces_up(self):
        verts, faces = ribbon_mesh([[0, 0, 0], [10, 0, 0]], width=2.0, depth=0.02)
        ys = [v[1] for v in verts]
        self.assertAlmostEqual(max(ys) - min(ys), 2.0)
        zs = [v[2] for v in verts]
        self.assertAlmostEqual(max(zs) - min(zs), 0.04)
        top = [verts[i] for i in faces[0]]
        a, b, c = top[0], top[1], top[2]
        u = [b[k] - a[k] for k in range(3)]
        w = [c[k] - a[k] for k in range(3)]
        normal_z = u[0] * w[1] - u[1] * w[0]
        self.assertGreater(normal_z, 0)
        self.assertEqual(len(faces), 4 + 2)                  # one segment: 4 sides + 2 caps

    def test_corner_keeps_its_width(self):
        verts, _ = ribbon_mesh([[0, 0, 0], [5, 0, 0], [5, 5, 0]], width=2.0)
        lt, rt = verts[4], verts[5]                          # the corner point's left/right top
        self.assertAlmostEqual(math.dist(lt[:2], rt[:2]), 2.0 * math.sqrt(2), places=4)

    def test_smoothing_passes_through_the_points(self):
        pts = [[0, 0, 0], [4, 2, 0], [8, 0, 0]]
        smooth = smooth_points(pts, samples=4)
        for p in pts:
            self.assertTrue(any(math.dist(p, q) < 1e-9 for q in smooth))

    def test_strokes_are_separate_pieces(self):
        verts, faces = strokes_mesh([[[-10, -10, 0], [10, 10, 0]], [[10, -10, 0], [-10, 10, 0]]], width=2.0, smooth=False)
        self.assertEqual(len(verts), 16)
        self.assertEqual(len(faces), 12)


class TestFlatPaths(unittest.TestCase):

    def test_path_named_curve_becomes_a_flat_strip(self):
        bridge = ScaledBridge()
        points = [[-10, -10, 0.02], [0, 0, 0.02], [10, 10, 0.02]]
        result = CreateCurveTool(bridge).execute({"name": "path_gravel", "points": points, "thickness": 1.0})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["profile"], "flat")
        self.assertAlmostEqual(result.data["width"], 2.0)
        box = bridge.measure_objects(["path_gravel"])
        self.assertLess(box["max"][2] - box["min"][2], 0.05)  # flat, not a 2 m tube
        self.assertEqual(bridge.get_object("path_gravel").type, "MESH")

    def test_explicit_flat_with_strokes(self):
        bridge = ScaledBridge()
        result = CreateCurveTool(bridge).execute({
            "name": "walkway", "profile": "flat", "width": 2.5,
            "strokes": [[[-10, -10, 0.02], [10, 10, 0.02]], [[10, -10, 0.02], [-10, 10, 0.02]]]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["strokes"], 2)
        # the X's two lines are not joined: nothing reaches the (10,10)->(10,-10) side
        verts = bridge.get_object("walkway").fake_vertices
        self.assertFalse(any(abs(v[0] - 10) < 0.5 and abs(v[1]) < 5 for v in verts))

    def test_ordinary_curves_stay_round(self):
        bridge = ScaledBridge()
        result = CreateCurveTool(bridge).execute({"name": "rope", "points": [[0, 0, 0], [1, 0, 1]], "thickness": 0.02})
        self.assertTrue(result.success, result.error)
        self.assertNotIn("profile", result.data)
        self.assertEqual(bridge.get_object("rope").type, "CURVE")

    def test_round_profile_can_be_forced_for_a_path_name(self):
        bridge = ScaledBridge()
        result = CreateCurveTool(bridge).execute({"name": "slide_path", "profile": "round",
                                                  "points": [[0, 0, 3], [2, 0, 0]], "thickness": 0.5})
        self.assertTrue(result.success, result.error)
        self.assertEqual(bridge.get_object("slide_path").type, "CURVE")

    def test_bad_profile_is_rejected(self):
        result = CreateCurveTool(ScaledBridge()).execute({"name": "x", "profile": "square", "points": [[0, 0, 0], [1, 0, 0]]})
        self.assertFalse(result.success)


class TestGroundRecipes(unittest.TestCase):

    def test_grass_and_aliases(self):
        for name in ("grass", "lawn", "Green Grass", "turf"):
            spec = sn.build_recipe(name)
            ramp = next(n for n in spec.nodes if n.type == "ValToRGB")
            light = ramp.ramp[-1][1]
            self.assertGreater(light[1], light[0], name)    # green, not brown
            self.assertGreater(light[1], light[2], name)

    def test_path_and_place_recipes_exist(self):
        for name in ("gravel", "concrete", "asphalt", "sand", "foliage", "pavement", "road", "beach", "stone"):
            self.assertTrue(sn.build_recipe(name).links, name)


if __name__ == "__main__":
    unittest.main()
