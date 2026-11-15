"""Regressions from the second "create a park" run (log 20261114_140347):

- 'palm_tree' was not in the library; six identical failures counted as six and the whole
  step (with the fountain already built) was undone;
- library.place called with name= instead of prefix=, so lamps were named street_lamp_*;
- a "3 m lamp" placed at scale 1.5 (5.85 m tall);
- render.setup preset 'outdoor' crashed on Blender 5.2's placeholder look identifier 'NONE'
  (covered in test_shader_nodes).
"""

from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.agent.repair_loop import RepairableExecutionLoop
from blender_ai_agent.tools.library_tools import LibraryPlaceTool, load_library, substitute_model
from .test_library_recipes import NodeBridge, _ensure_lights
from .test_repair_loop import build_repair_loop

_ensure_lights(NodeBridge)


def tool_response(*calls):
    return ModelResponse(content=None, tool_calls=[ToolCall(tool_name=n, arguments=a) for n, a in calls],
                         finish_reason="tool_calls")


def text_response(text="done"):
    return ModelResponse(content=text, tool_calls=[], finish_reason="stop")


class TestNewLibraryModels(unittest.TestCase):

    def test_palm_and_bench_exist_and_place(self):
        library = load_library()
        for model in ("palm_tree", "park_bench"):
            self.assertIn(model, library)
            bridge = NodeBridge()
            result = LibraryPlaceTool(bridge).execute({"model": model, "location": [2, 3, 0]})
            self.assertTrue(result.success, result.error)
            self.assertGreater(result.data["object_count"], 5, model)

    def test_palm_tree_is_about_seven_metres(self):
        self.assertAlmostEqual(load_library()["palm_tree"]["size"][2], 7.0, delta=0.5)

    def test_common_names_resolve(self):
        bridge = NodeBridge()
        for asked, expected in (("palm", "palm_tree"), ("Palm Tree", "palm_tree"), ("coconut_tree", "palm_tree"),
                                ("bench", "park_bench"), ("wooden_bench", "park_bench")):
            result = LibraryPlaceTool(bridge).execute({"model": asked, "prefix": f"t_{asked}_"})
            self.assertTrue(result.success, f"{asked}: {result.error}")
            self.assertEqual(result.data["model"], expected, asked)


class TestSubstitutes(unittest.TestCase):

    def test_close_stand_ins(self):
        self.assertEqual(substitute_model("tall_palm_tree"), "palm_tree")
        self.assertEqual(substitute_model("oak"), "round_tree")
        self.assertEqual(substitute_model("big_maple_tree"), "round_tree")
        self.assertEqual(substitute_model("hedge_row"), "bush")
        self.assertEqual(substitute_model("lamp_post_tall"), "street_lamp")
        self.assertIsNone(substitute_model("spaceship"))

    def test_place_reports_the_substitution(self):
        bridge = NodeBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "oak", "prefix": "park_oak1_"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["model"], "round_tree")
        self.assertIn("no 'oak'", result.data["note"])

    def test_truly_unknown_still_fails_with_the_list(self):
        result = LibraryPlaceTool(NodeBridge()).execute({"model": "spaceship"})
        self.assertFalse(result.success)
        self.assertIn("palm_tree", result.error)


class TestSizeAndNames(unittest.TestCase):

    def test_height_sets_the_real_size(self):
        bridge = NodeBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "street_lamp", "height": 3.0})
        self.assertTrue(result.success, result.error)
        self.assertAlmostEqual(result.data["size_m"][2], 3.0, places=2)

    def test_name_is_used_as_prefix_and_gets_an_underscore(self):
        bridge = NodeBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "street_lamp", "name": "park_lamp1"})
        self.assertTrue(result.success, result.error)
        self.assertTrue(all(n.startswith("park_lamp1_") for n in result.data["meshes"]), result.data["meshes"])


class TestRepeatedFailureCountsOnce(unittest.TestCase):

    def test_same_error_many_times_in_one_batch_does_not_undo_the_step(self):
        good = ("object.create", {"primitive": "CUBE", "name": "park_fountain"})
        bad = [("object.transform", {"name": f"palm{i}", "location": [i, 0, 0]}) for i in range(6)]
        loop, bridge, _ = build_repair_loop([tool_response(good, *bad), text_response("ok")])
        loop._max_failed_steps = 3
        result = loop.run("add palms")
        self.assertFalse(result.rolled_back)
        self.assertIsNotNone(bridge.get_object("park_fountain"))

    def test_different_errors_still_stop_the_step(self):
        good = ("object.create", {"primitive": "CUBE", "name": "park_fountain"})
        bad = [("object.transform", {"name": "ghost", "location": [0, 0, 0]}),
               ("mesh.nothing", {"name": "x"}),
               ("object.transform", {"name": "ghost"})]
        loop, _, _ = build_repair_loop([tool_response(good, *bad), text_response("ok")])
        loop._max_failed_steps = 3
        self.assertTrue(loop.run("add things").rolled_back)

    def test_error_signature_ignores_names_and_numbers(self):
        sig = RepairableExecutionLoop._error_signature
        self.assertEqual(sig("No model named 'palm_tree'. Available: a"), sig("No model named 'oak_3'. Available: a"))
        self.assertNotEqual(sig("No model named 'x'"), sig("Object 'x' not found"))


if __name__ == "__main__":
    unittest.main()
