from . import _bpy_stub  # noqa: F401

import math
import os
import tempfile
import unittest

from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.skills.builtins.campsite import CampsiteSkill
from blender_ai_agent.skills.builtins.library_props import LibraryPropSkill
from blender_ai_agent.skills.registry import SkillRegistry
from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.curve_tools import CreateCurveTool
from blender_ai_agent.tools.library_tools import (
    LibraryListTool, LibraryPlaceTool, find_model_by_alias, load_library,
)
from blender_ai_agent.tools.lighting_tools import CreateLightTool
from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool, ModifyMaterialTool
from blender_ai_agent.tools.models import PlaceModelInput
from blender_ai_agent.tools.object_tools import CreateObjectTool, TransformObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeObject
from .fakes_ext import FakeBridge
from .test_copilot_controller import FakeAgent
from .test_lighting_tools import FakeMapComposite, FakeRepeatedComposite

EXPECTED_MODELS = {"campfire", "torch", "lantern", "pine_tree", "round_tree", "bush", "rock", "log_seat",
                   "stool", "tent", "mushroom", "fence", "street_lamp", "cloud"}


def full_registry(bridge):
    registry = ToolRegistry()
    for tool in (CreateObjectTool, TransformObjectTool, CreateMaterialTool, AssignMaterialTool,
                 ModifyMaterialTool, CreateLightTool, CreateCurveTool, LibraryPlaceTool, LibraryListTool):
        registry.register(tool(bridge))
    registry.register(SceneInspectTool(SceneInspector(bridge)))
    return registry


class NoDownloadedModels(unittest.TestCase):
    """
    Hinglish: Skill ab (fallback ke liye) downloaded models ka index dekhti hai. In tests ko aapke asli
    ~/BlenderAIAgent/models se alag rakhte hain (khaali folder), warna "make a table" jaisa negative case
    aapke asli Table model se match ho jaata.
    """

    def setUp(self):
        super().setUp()
        self._empty_models = tempfile.TemporaryDirectory()
        self._old_models_dir = os.environ.get("BLENDER_AI_MODELS_DIR")
        os.environ["BLENDER_AI_MODELS_DIR"] = self._empty_models.name

    def tearDown(self):
        if self._old_models_dir is None:
            os.environ.pop("BLENDER_AI_MODELS_DIR", None)
        else:
            os.environ["BLENDER_AI_MODELS_DIR"] = self._old_models_dir
        self._empty_models.cleanup()
        super().tearDown()


class TestLibraryData(unittest.TestCase):

    def test_all_expected_models_exist(self):
        self.assertTrue(EXPECTED_MODELS <= set(load_library()))

    def test_every_model_is_well_formed(self):
        for name, spec in load_library().items():
            materials = set(spec["materials"])
            self.assertTrue(spec["parts"], name)
            self.assertEqual(len(spec["size"]), 3, name)
            names = [p["name"] for p in spec["parts"]]
            self.assertEqual(len(names), len(set(names)), f"duplicate part names in {name}")
            for part in spec["parts"]:
                self.assertIn(part["material"], materials, f"{name}.{part['name']}")
                self.assertEqual(len(part["offset"]), 3)
                self.assertEqual(len(part["rotation"]), 3)
                for number in part["offset"] + part["rotation"]:
                    self.assertTrue(math.isfinite(number))
                if part["kind"] == "curve":
                    self.assertGreaterEqual(len(part["points"]), 2, f"{name}.{part['name']}")
                    for point in part["points"]:
                        self.assertIn(len(point), (3, 4))
                    self.assertIn(part["curve_type"], ("BEZIER", "POLY", "NURBS"))
                elif part["kind"] == "mesh_data":
                    self.assertGreaterEqual(len(part["vertices"]), 3, f"{name}.{part['name']}")
                    for vertex in part["vertices"]:
                        self.assertEqual(len(vertex), 3)
                    for face in part["faces"]:
                        self.assertGreaterEqual(len(face), 3)
                        self.assertEqual(len(set(face)), len(face))
                        self.assertTrue(all(0 <= i < len(part["vertices"]) for i in face), f"{name}.{part['name']}")
                else:
                    self.assertIn(part["primitive"],
                                  ("CUBE", "SPHERE", "ICOSPHERE", "CYLINDER", "CONE", "PLANE", "TORUS"))
                    self.assertEqual(len(part["scale"]), 3)
            for key, mat in spec["materials"].items():
                self.assertEqual(len(mat["color"]), 3)
                if "emission" in mat:
                    self.assertGreater(mat["emission"]["strength"], 0)

    def test_fire_models_use_curves_for_flames_and_emissive_materials(self):
        campfire = load_library()["campfire"]
        flames = [p for p in campfire["parts"] if p["name"].startswith("flame")]
        self.assertGreaterEqual(len(flames), 6)
        self.assertTrue(all(p["kind"] == "curve" for p in flames))
        for p in flames:  # tapered: ends thinner than it starts
            self.assertLess(p["points"][-1][3], p["points"][0][3])
        self.assertGreater(campfire["materials"]["flame_outer"]["emission"]["strength"], 0)
        self.assertTrue(campfire["lights"])

    def test_tent_is_built_from_real_triangles_that_never_go_below_the_ground(self):
        """Screenshot: the old tent used buried diamonds, so without a ground plane it looked like a floating cube."""
        tent = load_library()["tent"]
        kinds = {p["name"]: p["kind"] for p in tent["parts"]}
        for name in ("panel_left", "panel_right", "end_front", "end_back", "floor"):
            self.assertEqual(kinds[name], "mesh_data", name)
        for part in tent["parts"]:
            if part["kind"] == "mesh_data":
                self.assertGreaterEqual(min(v[2] for v in part["vertices"]), 0.0, part["name"])
        end = next(p for p in tent["parts"] if p["name"] == "end_front")
        self.assertEqual((len(end["vertices"]), end["faces"]), (3, [[0, 1, 2]]))              # a real triangle

    def test_aliases(self):
        for alias, model in (("fire", "campfire"), ("aag", "campfire"), ("bonfire", "campfire"),
                             ("pine tree", "pine_tree"), ("Pine_Tree", "pine_tree"), ("tree", "round_tree"),
                             ("lamp post", "street_lamp"), ("mashal", "torch")):
            self.assertEqual(find_model_by_alias(alias), model, alias)
        self.assertIsNone(find_model_by_alias("spaceship"))


class TestPlaceModelInput(unittest.TestCase):

    def test_normalises_name_and_coerces_numbers(self):
        data = PlaceModelInput(model="Pine Tree", location="[1, 2, 0]", scale="1.5", yaw_degrees="90")
        self.assertEqual(data.model, "pine_tree")
        self.assertEqual(data.location, [1.0, 2.0, 0.0])
        self.assertEqual(data.scale, 1.5)

    def test_proto_containers_and_colour_formats(self):
        data = PlaceModelInput(model="rock", location=FakeRepeatedComposite([0, 0, 0]),
                               colors=FakeMapComposite({"rock": FakeRepeatedComposite([0.1, 0.2, 0.3]),
                                                        "x": "orange"}))
        self.assertEqual(data.colors["rock"], [0.1, 0.2, 0.3])
        self.assertEqual(data.colors["x"], [1.0, 0.5, 0.0])

    def test_rejects_bad_values(self):
        for kwargs in ({"scale": 0}, {"scale": 100}, {"location": [0, 0]}, {"yaw_degrees": "x"}, {"colors": 5}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                PlaceModelInput(model="rock", **kwargs)


class TestLibraryPlaceTool(unittest.TestCase):

    def test_every_model_places_and_all_parts_get_a_material(self):
        for model in sorted(load_library()):
            bridge = FakeBridge()
            result = LibraryPlaceTool(bridge).execute({"model": model, "location": [1, 2, 0]})
            self.assertTrue(result.success, f"{model}: {result.error}")
            spec = load_library()[model]
            self.assertEqual(result.data["object_count"], len(spec["parts"]), model)
            self.assertEqual(len(result.data["lights"]), len(spec["lights"]), model)
            for name in result.data["meshes"] + result.data["curves"]:
                self.assertIsNotNone(bridge.get_object(name).material_name, f"{model}:{name}")

    def test_campfire_has_curved_flames_glowing_materials_and_a_warm_light(self):
        bridge = FakeBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "campfire"})

        self.assertEqual(len(result.data["curves"]), 19)
        self.assertGreater(bridge.get_material("campfire_flame_outer_mat").emission_strength, 0)
        self.assertGreater(bridge.get_material("campfire_flame_inner_mat").emission_strength, 0)
        self.assertEqual(bridge.get_material("campfire_stone_mat").emission_strength, 0.0)
        light = bridge.get_object(result.data["lights"][0])
        self.assertEqual(light.light_type, "POINT")
        self.assertGreater(light.light_color[0], light.light_color[2])

    def test_location_scale_and_yaw_math(self):
        spec = load_library()["fence"]
        post = next(p for p in spec["parts"] if p["name"] == "post3")   # offset (1, 0, 0.5)
        self.assertEqual(post["offset"][:2], [1.0, 0.0])

        bridge = FakeBridge()
        result = LibraryPlaceTool(bridge).execute(
            {"model": "fence", "location": [10, 20, 0], "scale": 2, "yaw_degrees": 90})
        obj = bridge.get_object("fence_post3")
        # offset (1,0,0.5) * scale 2 = (2,0,1); yaw 90 deg turns +X into +Y -> world (10, 22, 1)
        self.assertAlmostEqual(obj.location[0], 10.0, places=6)
        self.assertAlmostEqual(obj.location[1], 22.0, places=6)
        self.assertAlmostEqual(obj.location[2], 1.0, places=6)
        self.assertAlmostEqual(obj.rotation_euler[2], math.pi / 2)          # yaw added to part rotation
        self.assertEqual(list(obj.scale), [0.05 * 2, 0.05 * 2, 0.5 * 2])     # part scale * scale
        self.assertEqual(result.data["size_m"], [4.2, 0.2, 2.0])

    def test_scale_applies_to_curves_and_light_brightness(self):
        bridge = FakeBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "campfire", "scale": 2})
        curve = bridge.get_object(result.data["curves"][0])
        self.assertEqual(list(curve.scale), [2, 2, 2])
        light = bridge.get_object(result.data["lights"][0])
        self.assertEqual(light.light_energy, 900 * 4)  # energy scales with area

    def test_colors_override(self):
        bridge = FakeBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "pine_tree", "colors": {"leaves": [1, 0, 0]}})
        self.assertTrue(result.success, result.error)
        self.assertEqual(bridge.get_material("pine_tree_leaves_mat").color[:3], [1, 0, 0])
        bad = LibraryPlaceTool(bridge).execute({"model": "pine_tree", "colors": {"roof": [1, 0, 0]}})
        self.assertFalse(bad.success)
        self.assertIn("leaves", bad.error)

    def test_unknown_model_lists_available_and_alias_is_resolved(self):
        tool = LibraryPlaceTool(FakeBridge())
        failed = tool.execute({"model": "spaceship"})
        self.assertFalse(failed.success)
        self.assertIn("campfire", failed.error)
        self.assertEqual(tool.execute({"model": "aag"}).data["model"], "campfire")

    def test_placing_twice_does_not_edit_the_first_copy(self):
        bridge = FakeBridge()
        tool = LibraryPlaceTool(bridge)
        first = tool.execute({"model": "rock", "location": [0, 0, 0], "prefix": "r_"})
        second = tool.execute({"model": "rock", "location": [5, 0, 0], "prefix": "r_"})
        self.assertTrue(first.success and second.success)
        self.assertEqual(bridge.get_object(first.data["meshes"][0]).location[0], 0)
        self.assertNotEqual(first.data["meshes"][0], second.data["meshes"][0])

    def test_metadata(self):
        tool = LibraryPlaceTool(FakeBridge())
        self.assertEqual(tool.name, "library.place")
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)
        self.assertEqual(LibraryListTool().permission, Permission.READ_ONLY)


class TestLibraryListTool(unittest.TestCase):

    def test_lists_everything_or_by_category(self):
        everything = LibraryListTool().execute({})
        self.assertEqual({m["model"] for m in everything.data["models"]}, set(load_library()))
        fire = LibraryListTool().execute({"category": "fire"})
        self.assertEqual({m["model"] for m in fire.data["models"]}, {"campfire", "torch"})
        self.assertFalse(LibraryListTool().execute({"category": "vehicles"}).success)

    def test_entries_have_what_the_llm_needs(self):
        entry = LibraryListTool().execute({"category": "nature"}).data["models"][0]
        for key in ("model", "category", "size_m", "description", "color_keys", "has_light"):
            self.assertIn(key, entry)


class TestLibraryPropSkill(NoDownloadedModels):

    def _skill(self, objects=None):
        bridge = FakeBridge(objects=objects)
        return LibraryPropSkill(ToolCaller(full_registry(bridge))), bridge

    def test_matches_only_short_place_requests(self):
        skill, _ = self._skill()
        for text in ("make a campfire", "Create a fire", "add a lantern please", "aag banao", "place the tent",
                     "build a pine tree.", "make me a rock", "bonfire banao", "add a street lamp"):
            self.assertGreaterEqual(skill.can_handle(text), 0.9, text)
        for text in ("make a campfire next to the tent", "add 3 trees", "make a red fire truck", "make a table",
                     "create a spaceship", "delete the fire", "move the tent left", "make a tree at 5, 5, 0"):
            self.assertEqual(skill.can_handle(text), 0.0, text)

    def test_places_the_model(self):
        skill, bridge = self._skill()
        result = skill.execute({"task": "make a campfire"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["model"], "campfire")
        self.assertIsNotNone(bridge.get_object("campfire_stone1"))

    def test_second_prop_goes_to_a_free_spot_not_on_top_of_the_first(self):
        skill, bridge = self._skill()
        skill.execute({"task": "make a campfire"})
        second = skill.execute({"task": "add a tent"})
        self.assertTrue(second.success, second.error)
        self.assertNotEqual(second.data["location"][:2], [0.0, 0.0])
        self.assertGreaterEqual(math.hypot(*second.data["location"][:2]), 3.0)

    def test_default_cube_in_the_way_is_avoided_and_ground_plane_is_ignored(self):
        ground = FakeObject(name="Ground", location=[0, 0, 0])
        ground.scale = [14, 14, 1]
        skill, _ = self._skill(objects=[FakeObject(name="Cube"), ground])
        result = skill.execute({"task": "make a rock"})
        self.assertTrue(result.success, result.error)
        self.assertNotEqual(result.data["location"][:2], [0.0, 0.0])   # cube is at the origin
        self.assertEqual(result.data["location"][:2], [3.0, 0.0])      # but the big ground did not push it away

    def test_works_without_scene_inspect(self):
        bridge = FakeBridge()
        registry = ToolRegistry()
        for tool in (CreateObjectTool, TransformObjectTool, CreateMaterialTool, AssignMaterialTool,
                     ModifyMaterialTool, CreateLightTool, CreateCurveTool, LibraryPlaceTool):
            registry.register(tool(bridge))
        result = LibraryPropSkill(ToolCaller(registry)).execute({"task": "make a lantern"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["location"], [0.0, 0.0, 0.0])

    def test_no_model_in_context_fails_cleanly(self):
        skill, _ = self._skill()
        self.assertFalse(skill.execute({}).success)

    def test_registry_prefers_campsite_for_whole_scene_and_library_for_single_props(self):
        bridge = FakeBridge()
        caller = ToolCaller(full_registry(bridge))
        registry = SkillRegistry()
        registry.register(CampsiteSkill(caller))
        registry.register(LibraryPropSkill(caller))
        self.assertEqual(registry.find_best_match("make a campsite").name, "campsite")
        self.assertEqual(registry.find_best_match("make a campfire").name, "library_props")
        self.assertEqual(registry.find_best_match("add a tent").name, "library_props")
        self.assertIsNone(registry.find_best_match("make a spinning donut"))


class TestLibraryThroughController(NoDownloadedModels):

    def test_make_a_fire_runs_without_the_llm(self):
        bridge = FakeBridge()
        caller = ToolCaller(full_registry(bridge))
        skills = SkillRegistry()
        skills.register(LibraryPropSkill(caller))
        agent = FakeAgent(results=[])   # would crash if the LLM were called
        controller = CopilotController(agent, skill_registry=skills, tool_caller=caller)

        result = controller.submit("make a fire")

        self.assertTrue(result.success, result.reply_text)
        self.assertEqual(agent.received_inputs, [])
        self.assertIsNotNone(bridge.get_object("campfire_flame_outer1"))
        self.assertEqual(bridge.get_object("campfire_flame_outer1").type, "CURVE")

    def test_longer_request_goes_to_the_llm(self):
        from .test_copilot_controller import FakeAgentResult
        bridge = FakeBridge()
        caller = ToolCaller(full_registry(bridge))
        skills = SkillRegistry()
        skills.register(LibraryPropSkill(caller))
        agent = FakeAgent(results=[FakeAgentResult(reply_text="ok")])
        controller = CopilotController(agent, skill_registry=skills, tool_caller=caller)

        controller.submit("make a campfire next to the red house")
        self.assertEqual(agent.received_inputs, ["make a campfire next to the red house"])


if __name__ == "__main__":
    unittest.main()