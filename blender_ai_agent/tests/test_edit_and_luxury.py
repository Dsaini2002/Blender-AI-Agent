"""Luxury room run (log 20261114_202551): a 'ceiling_lamp' became a 3.9 m street lamp through the ceiling, wall art was
a cloud, stools stood in for nightstands and the bed was single; renders were made while the vision quota was gone.
Plus: changing what is already there (colours, roof design), and the API key box with a Submit button."""

from . import _bpy_stub  # noqa: F401

import json
import os
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent.agent import post_verify as pv
from blender_ai_agent.agent import self_correct as sc
from blender_ai_agent.multi_agent.team import is_big_request, is_edit_request
from blender_ai_agent.tools import building
from blender_ai_agent.tools.building import BuildingInput, MeshBuildingTool, build
from blender_ai_agent.tools.colors import parse_color
from blender_ai_agent.tools.edit_tools import RecolorTool, resolve_names
from blender_ai_agent.tools.library_tools import LibraryPlaceTool, find_model_by_alias, load_library, substitute_model
from .test_hostel_campus import Bridge


class PropBridge(Bridge):
    """+ custom properties, as a saved .blend keeps them."""

    def __init__(self):
        super().__init__()
        self.props = {}

    def set_custom_prop(self, name, key, value):
        self.props[(name, key)] = value
        return True

    def get_custom_prop(self, name, key):
        return self.props.get((name, key)) if self.get_object(name) is not None else None


class TestIndoorModels(unittest.TestCase):

    def test_indoor_lights_never_become_a_street_lamp(self):
        for name, model in (("ceiling_lamp", "pendant_light"), ("ceiling_light_big", "pendant_light"),
                            ("bedside_lamp", "table_lamp"), ("luxury_chandelier", "chandelier"),
                            ("big_painting", "wall_art"), ("wall_art", "wall_art"), ("king_bed", "double_bed")):
            self.assertEqual(find_model_by_alias(name) or substitute_model(name), model, name)
        self.assertEqual(substitute_model("lamp_post"), "street_lamp")

    def test_new_models_exist_with_real_sizes(self):
        library = load_library()
        for name in ("double_bed", "nightstand", "table_lamp", "pendant_light", "chandelier", "floor_lamp", "rug",
                     "wall_art", "potted_plant", "armchair", "coffee_table", "tv_unit", "curtains", "mirror"):
            self.assertIn(name, library)
        self.assertGreater(library["double_bed"]["size"][0], 1.8)                   # king size, not single
        self.assertTrue(library["pendant_light"].get("hangs") and library["chandelier"].get("hangs"))
        self.assertTrue(library["wall_art"].get("hangs"))

    def test_hanging_light_stays_at_the_ceiling(self):
        bridge = Bridge()
        result = LibraryPlaceTool(bridge).execute({"model": "ceiling_lamp", "location": [0, 0, 3.0]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["model"], "pendant_light")
        self.assertIsNone(result.data["dropped_to_ground_m"])


class TestBuildingEdits(unittest.TestCase):

    def setUp(self):
        building.BUILT.clear()

    def test_roof_styles(self):
        for style, expect in (("flat", "flat"), ("sloped", "gable"), ("pitched", "gable"), ("hip", "hip"),
                              ("roof garden", "terrace")):
            self.assertEqual(BuildingInput(roof=style).roof, expect)
        with self.assertRaises(ValueError):
            BuildingInput(roof="spaceship")
        mesher, _info = build(BuildingInput(shape="U", floors=3, roof="gable"))
        self.assertTrue(mesher.boxes["roof"])
        _m, flat_info = build(BuildingInput(floors=3))
        _m, gable_info = build(BuildingInput(floors=3, roof="gable"))
        self.assertGreater(gable_info["height"], flat_info["height"])           # the ridge rises above the parapet
        mesher, _info = build(BuildingInput(floors=2, roof="terrace"))
        self.assertTrue(mesher.boxes["garden"])

    def test_same_name_rebuilds_in_place_and_keeps_the_rest(self):
        bridge = PropBridge()
        first = MeshBuildingTool(bridge).execute({"name": "hostel", "shape": "U", "floors": 6, "rooms": 180,
                                                  "location": [10, 5, 0], "wall_color": "cream"})
        self.assertTrue(first.success, first.error)
        count = len(bridge.get_objects())
        again = MeshBuildingTool(bridge).execute({"name": "hostel", "roof": "hip"})
        self.assertTrue(again.success, again.error)
        self.assertTrue(again.data["rebuilt"])
        self.assertEqual((again.data["floors"], again.data["shape"], again.data["roof"]), (6, "U", "hip"))
        self.assertEqual(len(bridge.get_objects()), count)                    # replaced, not duplicated
        self.assertFalse([o.name for o in bridge.get_objects() if ".00" in o.name])
        stored = json.loads(bridge.props[("hostel_structure", "aiagent_building")])
        self.assertEqual(stored["args"]["wall_color"], "cream")                # earlier choices remembered

    def test_edit_works_after_reopening_the_file(self):
        bridge = PropBridge()
        MeshBuildingTool(bridge).execute({"name": "block", "floors": 3, "location": [-40, 0, 0]})
        building.BUILT.clear()                                                # Blender restarted
        result = MeshBuildingTool(bridge).execute({"name": "block", "roof": "gable"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["floors"], 3)
        self.assertEqual(result.data["footprint_world"]["x"][0] < -40, True)   # still where it was

    def test_bad_edit_leaves_the_building_alone(self):
        bridge = PropBridge()
        MeshBuildingTool(bridge).execute({"name": "block", "floors": 3})
        count = len(bridge.get_objects())
        result = MeshBuildingTool(bridge).execute({"name": "block", "roof": "spaceship"})
        self.assertFalse(result.success)
        self.assertEqual(len(bridge.get_objects()), count)

    def test_materials_are_per_building(self):
        bridge = PropBridge()
        MeshBuildingTool(bridge).execute({"name": "a", "floors": 2})
        MeshBuildingTool(bridge).execute({"name": "b", "floors": 2, "location": [60, 0, 0]})
        self.assertEqual(bridge.get_object("a_walls").material_name, "a_white_wall")
        self.assertEqual(bridge.get_object("b_walls").material_name, "b_white_wall")


class TestRecolor(unittest.TestCase):

    def test_colour_words(self):
        self.assertEqual(parse_color("laal"), [0.75, 0.08, 0.06, 1.0])
        self.assertEqual(parse_color("#ff0000"), [1.0, 0.0, 0.0, 1.0])
        self.assertEqual(parse_color([255, 128, 0])[:3], [1.0, 128 / 255.0, 0.0])
        self.assertGreater(parse_color("light yellow")[2], parse_color("yellow")[2])
        self.assertLess(parse_color("dark blue")[2], parse_color("blue")[2])
        self.assertEqual(parse_color("a nice sky blue colour"), parse_color("sky blue"))
        with self.assertRaises(ValueError):
            parse_color("blurple-ish")

    def test_names_patterns_and_model_prefix(self):
        scene = ["sofa_sofa", "sofa_feet", "hostel_walls", "hostel_roof", "Cube"]
        self.assertEqual(resolve_names(["sofa"], scene), ["sofa_sofa"])                # the body, not the feet
        self.assertEqual(resolve_names(["hostel_*"], scene), ["hostel_walls", "hostel_roof"])
        self.assertEqual(resolve_names(["cube"], scene), ["Cube"])

    def test_recolor_changes_only_the_named_objects(self):
        bridge = Bridge()
        bridge.create_object("chair_a")
        bridge.create_object("chair_b")
        result = RecolorTool(bridge).execute({"names": ["chair_a"], "color": "navy"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["recolored"], ["chair_a"])
        self.assertIsNotNone(bridge.get_object("chair_a").material_name)
        self.assertIsNone(bridge.get_object("chair_b").material_name)
        missing = RecolorTool(bridge).execute({"names": ["nothing"], "color": "red"})
        self.assertFalse(missing.success)


class TestEditRouting(unittest.TestCase):

    def test_edits_are_not_new_scenes(self):
        for text in ("change the roof design of the hostel to sloped", "hostel ki walls ka colour cream karo",
                     "make the campus walls blue", "roof ka design badlo"):
            self.assertTrue(is_edit_request(text), text)
            self.assertFalse(is_big_request(text), text)
        self.assertTrue(is_big_request("create a luxury room with 3 walls"))

    def test_library_requests_do_not_go_to_script_building(self):
        from blender_ai_agent.skills.builtins.iterative_build import _library_has
        self.assertTrue(_library_has("add a chandelier"))
        self.assertTrue(_library_has("add a king size bed please"))
        self.assertFalse(_library_has("make a sports car"))


class TestVisionPause(unittest.TestCase):

    def test_quota_pauses_renders_and_no_other_ai_takes_over(self):
        verifier = pv.PostRunVerifier.__new__(pv.PostRunVerifier)
        cfg = sc.BuilderConfig(api_key="g", vision_provider="gemini")
        verifier._maybe_pause(cfg, "429 Quota exceeded. Please retry in 31s.")
        self.assertIn("paused", verifier._paused_reason(cfg))
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "c"}):
            same = verifier._fallback_vision(cfg)
        self.assertEqual((same.vision_provider, same.api_key), ("gemini", "g"))       # never another AI
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            os.environ.pop("CLAUDE_API_KEY", None)
            self.assertEqual(verifier._fallback_vision(cfg).vision_provider, "gemini")
        verifier._paused_until["gemini"] = time.time() - 1                     # quota back
        self.assertEqual(verifier._paused_reason(cfg), "")

    def test_other_errors_do_not_pause(self):
        verifier = pv.PostRunVerifier.__new__(pv.PostRunVerifier)
        cfg = sc.BuilderConfig(api_key="g")
        verifier._maybe_pause(cfg, "timeout")
        self.assertEqual(verifier._paused_reason(cfg), "")


class TestKeyBox(unittest.TestCase):

    def test_key_warnings(self):
        from blender_ai_agent.ui.panel import key_warning
        self.assertEqual(key_warning("claude", "sk-ant-abc"), "")
        self.assertIn("Claude", key_warning("claude", "AIzaXYZ"))
        self.assertIn("empty", key_warning("gemini", "  "))
        self.assertIn("space", key_warning("gemini", "AIza ab cd"))

    def test_submit_saves_the_key_and_connects(self):
        from blender_ai_agent import prefs
        from blender_ai_agent.ui import panel

        class Prefs:
            gemini_api_key = groq_api_key = openai_api_key = claude_api_key = ""

        saved = Prefs()
        scene = SimpleNamespace(aiagent_provider_choice="claude", aiagent_is_running=False)
        with mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(prefs, "get_prefs", return_value=saved), \
                mock.patch.object(prefs, "_save_preferences_soon"), \
                mock.patch.object(panel, "_apply_provider", return_value="Connected to Anthropic Claude"):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            message = panel.save_key(scene, "claude", "  sk-ant-test  ")
            self.assertEqual(saved.claude_api_key, "sk-ant-test")
            self.assertEqual(os.environ.get("ANTHROPIC_API_KEY"), "sk-ant-test")
            self.assertTrue(message.startswith("Connected"))
            prefs._applied.pop("ANTHROPIC_API_KEY", None)
        self.assertEqual(panel.save_key(scene, "claude", ""), "Paste the key first.")


if __name__ == "__main__":
    unittest.main()
