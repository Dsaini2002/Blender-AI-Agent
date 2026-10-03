from . import _bpy_stub  # noqa: F401

import math
import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.mesh_advanced_tools import (
    EditMeshInput, LatheInput, MeshEditTool, MeshHelpTool, MeshLatheTool, MeshPrismTool, MeshScriptTool,
    MeshSdfTool, MeshTerrainTool, PrismInput, ScriptMeshInput, SdfInput, TerrainInput,
)
from blender_ai_agent.tools.mesh_edit_runner import run_edit_on_parts
from .fakes import FakeObject
from .fakes_ext import FakeBridge
from .test_lighting_tools import FakeMapComposite, FakeRepeatedComposite
from .test_mesh_kit_engine import bottle, cube, edges_manifold, finite


def bridge_with(name="Bottle", vertices=None, faces=None):
    obj = FakeObject(name=name)
    verts, fcs = bottle(16, 10) if vertices is None else (vertices, faces)
    obj.mesh_vertices, obj.mesh_faces = [list(v) for v in verts], [list(f) for f in fcs]
    return FakeBridge(objects=[obj]), obj


class TestEditMeshInput(unittest.TestCase):

    def test_needs_something_to_do(self):
        with self.assertRaises(ValueError):
            EditMeshInput(object_name="B")
        with self.assertRaises(ValueError):
            EditMeshInput(object_name="")

    def test_preset_words_including_hinglish_and_numbers_as_text(self):
        for word in ("melted", "pighla hua", "Twisted", "toota", "rusty", "kaante wala", "cut in half"):
            data = EditMeshInput(object_name="B", preset=word, strength="0.7", seed="3.0")
            self.assertEqual(data.final_ops[0]["op"], "preset")
        self.assertEqual(data.strength, 0.7)
        self.assertEqual(data.seed, 3)
        with self.assertRaises(ValueError) as ctx:
            EditMeshInput(object_name="B", preset="explodingunicorn")
        self.assertIn("melted", str(ctx.exception))

    def test_ops_code_and_preset_are_combined_in_order(self):
        data = EditMeshInput(object_name="B", preset="bent", select="top", ops=[{"op": "twist", "angle": 40}], code="dz = 0.01")
        self.assertEqual([o["op"] for o in data.final_ops], ["preset", "twist", "script"])
        self.assertEqual(data.final_ops[0]["select"], "top")
        self.assertEqual(data.final_ops[2]["select"], "top")

    def test_ops_arrive_in_llm_formats(self):
        proto = EditMeshInput(object_name="B", ops=FakeRepeatedComposite([FakeMapComposite({"op": "noise", "amplitude": "0.02"})]))
        self.assertEqual(proto.final_ops[0]["op"], "noise")
        single = EditMeshInput(object_name="B", ops={"op": "smooth"})                  # akela dict bhi chalega
        self.assertEqual(len(single.final_ops), 1)

    def test_bad_ops_and_code_are_rejected_with_clear_messages(self):
        for kwargs, fragment in (({"ops": [{"op": "wobble"}]}, "unknown operator"), ({"ops": [{"angle": 3}]}, "'op' key"),
                                 ({"ops": [{"op": "move", "select": "sideways"}]}, "select"), ({"code": "import os"}, "script"),
                                 ({"code": "dz = foo"}, "unknown name"), ({"preset": "bent", "detail": 5}, "detail")):
            with self.assertRaises(ValueError, msg=str(kwargs)) as ctx:
                EditMeshInput(object_name="B", **kwargs)
            self.assertIn(fragment, str(ctx.exception), str(kwargs))


class TestMeshEditTool(unittest.TestCase):

    def test_the_bottle_example_end_to_end(self):
        bridge, obj = bridge_with()
        result = MeshEditTool(bridge).execute({"object_name": "Bottle", "preset": "broken", "region": "neck", "strength": 0.4})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["operators"], ["preset:broken"])
        self.assertTrue(result.data["uv_preserved"])                          # sirf vertices hile / faces hate
        before = bottle(16, 10)[0]
        top_before = max(v[2] for v in before)
        self.assertLess(max(v[2] for v in obj.mesh_vertices), top_before)       # upar ka kinara tooota
        self.assertGreater(result.data["removed_faces"], 0)

    def test_melted_changes_topology_and_reports_uv_reset(self):
        bridge, obj = bridge_with()
        result = MeshEditTool(bridge).execute({"object_name": "Bottle", "preset": "pighla hua", "strength": 0.6})
        self.assertTrue(result.success, result.error)
        self.assertFalse(result.data["uv_preserved"])
        self.assertGreater(len(obj.mesh_faces), len(bottle(16, 10)[1]))
        self.assertTrue(finite(obj.mesh_vertices))

    def test_composed_operators_and_script(self):
        bridge, obj = bridge_with()
        result = MeshEditTool(bridge).execute({
            "object_name": "Bottle",
            "ops": [{"op": "twist", "angle": 90, "select": "top"}, {"op": "inflate", "amount": 0.03}],
            "code": "dz = 0.02 * sin(u * 10)"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["operators"], ["twist", "inflate", "script"])
        self.assertEqual(len(result.data["notes"]), 3)

    def test_cut_in_half(self):
        bridge, obj = bridge_with(vertices=cube()[0], faces=cube()[1])
        result = MeshEditTool(bridge).execute({"object_name": "Bottle", "preset": "sliced"})
        self.assertTrue(result.success, result.error)
        self.assertAlmostEqual(max(v[2] for v in obj.mesh_vertices), 0.5)
        self.assertTrue(all(c == 2 for c in edges_manifold(obj.mesh_faces).values()))

    def test_failures_are_clean(self):
        bridge, _ = bridge_with()
        self.assertIn("not found", MeshEditTool(bridge).execute({"object_name": "Ghost", "preset": "bent"}).error)
        light = FakeBridge(objects=[FakeObject(name="Lamp", type_="LIGHT")])
        self.assertFalse(MeshEditTool(light).execute({"object_name": "Lamp", "preset": "bent"}).success)
        bad = MeshEditTool(bridge).execute({"object_name": "Bottle", "preset": "nonsense"})
        self.assertFalse(bad.success)
        self.assertIn("Presets", bad.error)
        bad_cut = MeshEditTool(bridge).execute({"object_name": "Bottle", "ops": [{"op": "cut", "axis": "z", "value": -50, "keep": "below"}]})
        self.assertFalse(bad_cut.success)
        self.assertIn("whole mesh", bad_cut.error)

    def test_metadata_tells_the_model_never_to_refuse(self):
        tool = MeshEditTool(FakeBridge())
        self.assertEqual((tool.name, tool.permission), ("mesh.edit", Permission.SAFE_WRITE))
        for word in ("NEVER", "preset", "ops", "mesh.help", "melted", "select"):
            self.assertIn(word, tool.description)


class TestMeshScriptTool(unittest.TestCase):

    def test_runs_a_formula(self):
        bridge, obj = bridge_with()
        result = MeshScriptTool(bridge).execute({"object_name": "Bottle", "code": "dz = 0.05 * sin(u * 12)", "select": "top"})
        self.assertTrue(result.success, result.error)
        self.assertTrue(finite(obj.mesh_vertices))

    def test_dangerous_or_broken_code_is_a_clean_failure(self):
        bridge, _ = bridge_with()
        for code in ("import os", "dx = open('x')", "while True:\n    dx = 1", "dz = x.real", "dz = foo"):
            result = MeshScriptTool(bridge).execute({"object_name": "Bottle", "code": code})
            self.assertFalse(result.success, code)
            self.assertTrue(result.error)

    def test_missing_object(self):
        self.assertFalse(MeshScriptTool(FakeBridge()).execute({"object_name": "Ghost", "code": "dz = 1"}).success)


class TestRunnerWithSeveralParts(unittest.TestCase):

    def parts(self):
        body, body_faces = bottle(12, 8)
        cap = [(x * 0.5, y * 0.5, z + 3.0) for x, y, z in [(v[0], v[1], v[2] / 3.0) for v in body]]
        return [{"name": "Body", "vertices": body, "faces": body_faces}, {"name": "Cap", "vertices": cap, "faces": body_faces}]

    def test_effects_are_applied_to_the_whole_model_not_per_part(self):
        results, _ = run_edit_on_parts(self.parts(), [{"op": "twist", "angle": 180, "centered": False}])
        body, cap = results
        self.assertFalse(body["topology_changed"])
        self.assertEqual(len(body["vertices"]), len(self.parts()[0]["vertices"]))
        top_y = max(v[2] for v in cap["vertices"])
        self.assertGreater(top_y, 3.5)
        # twist poore model (z 0..4) par: Body ka upar wala kinara Cap ke neeche wale kinare se mel khaata hai (continuous)
        body_top = [v for v in body["vertices"] if abs(v[2] - 3.0) < 1e-6]
        cap_bottom = [v for v in cap["vertices"] if abs(v[2] - 3.0) < 1e-6]
        self.assertTrue(body_top and cap_bottom)

    def test_removed_faces_are_mapped_back_to_the_right_part(self):
        results, _ = run_edit_on_parts(self.parts(), [{"op": "holes", "fraction": 0.3, "seed": 2}])
        removed_total = sum(len(r["removed_faces"]) for r in results)
        self.assertGreater(removed_total, 0)
        for r in results:
            self.assertTrue(all(0 <= f < r["orig_faces"] for f in r["removed_faces"]))

    def test_topology_change_is_split_back_into_parts(self):
        results, notes = run_edit_on_parts(self.parts(), [{"op": "subdivide", "levels": 1}])
        for r in results:
            self.assertTrue(r["topology_changed"])
            self.assertEqual(len(r["faces"]), 4 * r["orig_faces"])
            self.assertEqual(len(r["faces"]), len(r["face_source"]))
            self.assertTrue(all(0 <= s < r["orig_faces"] for s in r["face_source"]))
            self.assertTrue(all(0 <= i < len(r["vertices"]) for f in r["faces"] for i in f))
        cut, _ = run_edit_on_parts(self.parts(), [{"op": "cut", "axis": "z", "at": 0.6, "keep": "below", "cap": True}])
        self.assertTrue(all(finite(r["vertices"]) for r in cut))
        self.assertTrue(any(-1 in r["face_source"] for r in cut))                # cap bana

    def test_empty_parts(self):
        with self.assertRaises(ValueError):
            run_edit_on_parts([], [{"op": "smooth"}])


class TestGeneratorInputs(unittest.TestCase):

    def test_lathe_input(self):
        self.assertEqual(LatheInput(name="V", preset="Wine Glass").preset, "wine_glass")
        data = LatheInput(name="V", profile=[["0", "0"], [0.3, 0.5]], height="2", radius="0.4", thickness="0.1", segments="24.0")
        self.assertEqual((data.height, data.thickness, data.segments), (2.0, 0.1, 24))
        for bad in ({}, {"preset": "spaceship"}, {"profile": [[1, 0]]}, {"preset": "vase", "thickness": 2}, {"preset": "vase", "height": 0},
                    {"preset": "vase", "segments": 2}, {"profile": [[1, 2, 3], [1, 1]]}):
            with self.assertRaises(ValueError, msg=str(bad)):
                LatheInput(name="V", **bad)

    def test_terrain_input(self):
        self.assertEqual(TerrainInput(name="T", size=12).size, [12.0, 12.0])
        self.assertEqual(TerrainInput(name="T", size=["20", 10]).size, [20.0, 10.0])
        for bad in ({"style": "lava"}, {"size": [1, 2, 3]}, {"size": 5000}, {"resolution": 2}, {"resolution": 999}):
            with self.assertRaises(ValueError, msg=str(bad)):
                TerrainInput(name="T", **bad)

    def test_sdf_input(self):
        data = SdfInput(name="S", shapes={"type": "sphere", "radius": "0.5"})
        self.assertEqual(len(data.shapes), 1)
        for bad in ({"shapes": []}, {"shapes": [{"type": "teapot"}]}, {"shapes": [{"type": "sphere"}, {"op": "xor"}]},
                    {"shapes": [{"type": "sphere"}], "resolution": 3}, {"shapes": [{"type": "sphere"}], "bounds": [1, 2]},
                    {"shapes": ["sphere"]}, {"shapes": [{"type": "sphere"}] * 40}):
            with self.assertRaises(ValueError, msg=str(bad)):
                SdfInput(name="S", **bad)

    def test_prism_input(self):
        self.assertEqual(PrismInput(name="P", kind="Rounded Rect").kind, "rounded_rect")
        self.assertEqual(PrismInput(name="P", polygon=[["0", "0"], [1, 0], [0, 1]]).polygon[0], [0.0, 0.0])
        for bad in ({}, {"kind": "blob"}, {"polygon": [[0, 0], [1, 1]]}, {"kind": "star", "height": 0}):
            with self.assertRaises(ValueError, msg=str(bad)):
                PrismInput(name="P", **bad)


class TestGeneratorTools(unittest.TestCase):

    def test_lathe_bottle(self):
        bridge = FakeBridge()
        result = MeshLatheTool(bridge).execute({"name": "Bottle", "preset": "bottle", "height": 0.3, "radius": 0.04})
        self.assertTrue(result.success, result.error)
        obj = bridge.get_object("Bottle")
        self.assertEqual(obj.type, "MESH")
        self.assertAlmostEqual(max(v[2] for v in obj.mesh_vertices), 0.3)
        self.assertTrue(obj.shade_smooth)

    def test_lathe_custom_profile_partial_and_name_collision(self):
        bridge = FakeBridge()
        tool = MeshLatheTool(bridge)
        self.assertTrue(tool.execute({"name": "Cup", "profile": [[0, 0], [0.3, 0], [0.3, 0.5]], "thickness": 0.1}).success)
        self.assertTrue(tool.execute({"name": "Half", "preset": "vase", "angle_degrees": 180}).success)
        self.assertEqual(tool.execute({"name": "Cup", "preset": "cup"}).data["name"], "Cup.001")

    def test_terrain_sdf_prism(self):
        bridge = FakeBridge()
        ground = MeshTerrainTool(bridge).execute({"name": "Ground", "size": 12, "resolution": 20, "style": "hills", "flat_radius": 0.5})
        self.assertTrue(ground.success, ground.error)
        self.assertEqual(ground.data["face_count"], 400)
        rock = MeshSdfTool(bridge).execute({"name": "Rock", "shapes": [{"type": "sphere", "radius": 0.5}], "resolution": 20, "roughness": 0.05})
        self.assertTrue(rock.success, rock.error)
        self.assertGreater(rock.data["face_count"], 100)
        gear = MeshPrismTool(bridge).execute({"name": "Gear", "kind": "gear", "sides": 10, "radius": 0.5, "height": 0.1})
        self.assertTrue(gear.success, gear.error)

    def test_llm_style_arguments(self):
        bridge = FakeBridge()
        result = MeshSdfTool(bridge).execute({"name": "Snowman", "resolution": "24.0", "location": "1, 2, 0", "shapes": [
            {"type": "sphere", "radius": "0.5", "center": ["0", "0", "0.5"]},
            {"type": "sphere", "radius": 0.35, "center": {"x": 0, "y": 0, "z": 1.2}, "op": "smooth_union", "k": 0.1}]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(bridge.get_object("Snowman").location, [1.0, 2.0, 0.0])

    def test_empty_sdf_result_is_a_clean_failure(self):
        result = MeshSdfTool(FakeBridge()).execute({"name": "Nothing", "resolution": 16, "shapes": [
            {"type": "sphere", "radius": 0.3}, {"type": "sphere", "radius": 0.5, "op": "subtract"}]})
        self.assertFalse(result.success)
        self.assertIn("no surface", result.error)

    def test_metadata(self):
        for cls, name in ((MeshLatheTool, "mesh.lathe"), (MeshTerrainTool, "mesh.terrain"), (MeshSdfTool, "mesh.sdf"),
                          (MeshPrismTool, "mesh.prism"), (MeshScriptTool, "mesh.script"), (MeshHelpTool, "mesh.help")):
            tool = cls(FakeBridge())
            self.assertEqual(tool.name, name)
            self.assertTrue(len(tool.description) > 80)
        self.assertEqual(MeshHelpTool().permission, Permission.READ_ONLY)


class TestMeshHelp(unittest.TestCase):

    def test_lists_everything_the_agent_needs(self):
        data = MeshHelpTool().execute({}).data
        for key in ("operators", "presets", "selectors", "generators", "examples"):
            self.assertIn(key, data)
        self.assertIn("melted", data["presets"])
        self.assertIn("twist", data["operators"])
        self.assertIn("mesh.lathe", data["generators"])
        only = MeshHelpTool().execute({"topic": "presets"}).data
        self.assertEqual(set(only), {"presets", "preset_synonyms_examples"})
        self.assertFalse(MeshHelpTool().execute({"topic": "cooking"}).success)


if __name__ == "__main__":
    unittest.main()