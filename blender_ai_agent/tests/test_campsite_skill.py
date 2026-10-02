from . import _bpy_stub  # noqa: F401

import math
import unittest

from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.skills.builtins.campsite import CampsiteSkill
from blender_ai_agent.skills.builtins.house_builder import HouseBuilderSkill
from blender_ai_agent.skills.registry import SkillRegistry
from blender_ai_agent.tools.camera_tools import CreateCameraTool, SetCameraTool
from blender_ai_agent.tools.lighting_tools import CreateLightTool, SetWorldTool
from blender_ai_agent.tools.material_tools import AssignMaterialTool, CreateMaterialTool, ModifyMaterialTool
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.tools.object_tools import CreateObjectTool, DeleteObjectTool, TransformObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge, FakeObject


def build_skill(skip_tools=(), objects=None, with_scene=False):
    bridge = FakeBridge(objects=list(objects) if objects else None)
    registry = ToolRegistry()
    for tool in (CreateObjectTool, TransformObjectTool, CreateMaterialTool, AssignMaterialTool,
                 ModifyMaterialTool, CreateLightTool, SetWorldTool, CreateCameraTool, SetCameraTool):
        if tool.name not in skip_tools:
            registry.register(tool(bridge))
    if with_scene:
        registry.register(DeleteObjectTool(bridge))
        registry.register(SceneInspectTool(SceneInspector(bridge)))
    return CampsiteSkill(ToolCaller(registry)), bridge


class TestCampsiteRouting(unittest.TestCase):

    def test_can_handle_camping_requests(self):
        skill, _ = build_skill()
        for text in ("make a campsite", "build a campfire scene", "create a tent", "camping at night",
                     "camp site please", "bonfire"):
            self.assertEqual(skill.can_handle(text), 1.0, text)

    def test_ignores_unrelated_requests(self):
        skill, _ = build_skill()
        for text in ("make a house", "start a campaign", "create a table", "add some content"):
            self.assertEqual(skill.can_handle(text), 0.0, text)

    def test_registry_picks_campsite_over_house(self):
        bridge = FakeBridge()
        caller = ToolCaller(ToolRegistry())
        registry = SkillRegistry()
        registry.register(HouseBuilderSkill(caller))
        registry.register(CampsiteSkill(caller))
        self.assertEqual(registry.find_best_match("make a campsite").name, "campsite")
        self.assertEqual(registry.find_best_match("make a house").name, "house_builder")


class TestCampsiteBuild(unittest.TestCase):

    def test_builds_every_part_category(self):
        skill, bridge = build_skill()
        result = skill.execute({})

        self.assertTrue(result.success, result.error)
        parts = result.data["parts"]
        for category in ("ground", "tent", "campfire", "props", "rocks", "trees", "sky", "lights"):
            self.assertTrue(parts.get(category), f"missing category {category}")
        # every reported part really exists in the scene
        for names in parts.values():
            for name in names:
                self.assertIsNotNone(bridge.get_object(name), name)

    def test_tent_is_two_panels_whose_tops_meet_at_the_ridge(self):
        skill, bridge = build_skill()
        skill.execute({"camp_name": "C"})

        left, right = bridge.get_object("C_PanelLeft"), bridge.get_object("C_PanelRight")
        self.assertIsNotNone(left)
        self.assertIsNotNone(right)
        # Tilt angles are mirrored, so the A-frame is symmetric
        self.assertAlmostEqual(left.rotation_euler[0], -right.rotation_euler[0])

        # Top-centre of each panel (local +Z * half slant, tilted about X, then yawed about Z)
        def top(obj):
            half = obj.scale[2]
            phi, yaw = obj.rotation_euler[0], obj.rotation_euler[2]
            ly, lz = -math.sin(phi) * half, math.cos(phi) * half
            x = -ly * math.sin(yaw)
            y = ly * math.cos(yaw)
            return (obj.location[0] + x, obj.location[1] + y, obj.location[2] + lz)

        tl, tr = top(left), top(right)
        for a, b in zip(tl, tr):
            self.assertAlmostEqual(a, b, places=6)
        self.assertAlmostEqual(tl[2], 1.1, places=6)  # ridge height h

    def test_flames_are_emissive_and_wood_is_not(self):
        skill, bridge = build_skill()
        skill.execute({"camp_name": "C"})
        self.assertGreater(bridge.get_material("C_FlameOuter_Mat").emission_strength, 0)
        self.assertGreater(bridge.get_material("C_FlameInner_Mat").emission_strength, 0)
        self.assertGreater(bridge.get_material("C_Moon_Mat").emission_strength, 0)
        self.assertEqual(bridge.get_material("C_Wood_Mat").emission_strength, 0.0)

    def test_materials_are_shared_not_one_per_object(self):
        skill, bridge = build_skill()
        result = skill.execute({"camp_name": "C", "tree_count": 5})
        trees = result.data["parts"]["trees"]
        leaf_users = [n for n in trees if "Tier" in n]
        self.assertEqual(len(leaf_users), 15)
        self.assertEqual({bridge.get_object(n).material_name for n in leaf_users}, {"C_PineLeaves_Mat"})

    def test_night_lighting_setup(self):
        skill, bridge = build_skill()
        skill.execute({"camp_name": "C"})

        fire = bridge.get_object("C_FireLight")
        moon = bridge.get_object("C_MoonLight")
        self.assertEqual(fire.light_type, "POINT")
        self.assertGreater(fire.light_color[0], fire.light_color[2])  # warm
        self.assertEqual(moon.light_type, "SUN")
        self.assertGreater(moon.light_color[2], moon.light_color[0])  # cool
        self.assertIsNotNone(bridge.get_object("C_RimGreen"))
        self.assertIsNotNone(bridge.get_object("C_RimPurple"))
        self.assertLess(bridge.world["strength"], 0.5)
        self.assertLess(sum(bridge.world["color"]), 0.5)  # dark sky

    def test_day_mode_uses_bright_sky_and_no_moon(self):
        skill, bridge = build_skill()
        result = skill.execute({"camp_name": "C", "night": False})
        self.assertTrue(result.success, result.error)
        self.assertIsNone(bridge.get_object("C_Moon"))
        self.assertIsNone(bridge.get_object("C_RimGreen"))
        self.assertIsNotNone(bridge.get_object("C_Sun"))
        self.assertEqual(bridge._active_camera is not None, True)
        self.assertGreaterEqual(bridge.world["strength"], 1.0)

    def test_camera_is_created_set_active_and_aimed_at_the_scene(self):
        skill, bridge = build_skill()
        result = skill.execute({"camp_name": "C"})
        cam = bridge.get_object(result.data["camera"])
        self.assertIs(bridge._active_camera, cam)
        self.assertLess(cam.location[1], 0)  # in front of the scene
        self.assertTrue(0 < cam.rotation_euler[0] < math.pi / 2)

    def test_camera_can_be_skipped(self):
        skill, bridge = build_skill()
        result = skill.execute({"add_camera": False})
        self.assertTrue(result.success)
        self.assertIsNone(result.data["camera"])
        self.assertIsNone(bridge._active_camera)

    def test_tree_and_rock_counts(self):
        skill, _ = build_skill()
        result = skill.execute({"tree_count": 3, "rock_count": 2})
        trees = [n for n in result.data["parts"]["trees"] if n.endswith("_Trunk")]
        self.assertEqual(len(trees), 3)
        self.assertEqual(len(result.data["parts"]["rocks"]), 2)

        empty, _ = build_skill()
        result = empty.execute({"tree_count": 0, "rock_count": 0})
        self.assertTrue(result.success)
        self.assertNotIn("trees", result.data["parts"])

    def test_placement_is_deterministic_per_seed(self):
        def positions(seed):
            skill, bridge = build_skill()
            result = skill.execute({"camp_name": "C", "seed": seed})
            names = result.data["parts"]["trees"] + result.data["parts"]["rocks"]
            return [tuple(bridge.get_object(n).location) for n in names]

        self.assertEqual(positions(1), positions(1))
        self.assertNotEqual(positions(1), positions(2))

    def test_trees_and_rocks_stay_clear_of_the_fire_and_tent(self):
        skill, bridge = build_skill()
        result = skill.execute({"camp_name": "C", "tree_count": 10, "rock_count": 8})
        for name in result.data["parts"]["trees"] + result.data["parts"]["rocks"]:
            x, y, _ = bridge.get_object(name).location
            self.assertGreater(math.hypot(x, y), 1.4, name)  # not on the fire

    def test_location_offsets_the_whole_scene(self):
        skill, bridge = build_skill()
        skill.execute({"camp_name": "C", "location": [10, 20, 0]})
        ground = bridge.get_object("C_Ground")
        self.assertEqual(list(ground.location), [10, 20, 0])
        self.assertEqual(list(bridge.get_object("C_FireLight").location), [10, 20, 0.9])

    def test_two_campsites_with_different_names_coexist(self):
        skill, bridge = build_skill()
        self.assertTrue(skill.execute({"camp_name": "A", "location": [0, 0, 0]}).success)
        self.assertTrue(skill.execute({"camp_name": "B", "location": [50, 0, 0]}).success)
        self.assertIsNotNone(bridge.get_object("A_Ground"))
        self.assertIsNotNone(bridge.get_object("B_Ground"))

    def test_running_the_skill_twice_does_not_leak_state(self):
        skill, _ = build_skill()
        first = skill.execute({"camp_name": "A", "rock_count": 4}).data["object_count"]
        second = skill.execute({"camp_name": "B", "rock_count": 4}).data["object_count"]
        self.assertEqual(first, second)


class TestLeftoverDefaults(unittest.TestCase):
    """Agent ko pata hai ki startup Cube/Light scene mein pade hain — ab wo ignore nahi karta,
    na chupchaap delete karta hai; poochta hai (ya user ke kehne par hataata hai)."""

    @staticmethod
    def _defaults():
        return [FakeObject(name="Cube"), FakeObject(name="Light", type_="LIGHT", location=[4.0, 1.0, 6.0])]

    def test_asks_instead_of_silently_deleting(self):
        skill, bridge = build_skill(objects=self._defaults(), with_scene=True)

        result = skill.execute({"camp_name": "C"})

        self.assertTrue(result.success, result.error)
        # nothing was deleted behind the user's back
        self.assertIsNotNone(bridge.get_object("Cube"))
        self.assertIsNotNone(bridge.get_object("Light"))
        self.assertEqual(result.data["leftover_defaults"], ["Cube", "Light"])
        notes = " ".join(result.data["notes"])
        self.assertIn("default 'Cube'", notes)
        self.assertIn("right where the campfire is", notes)  # it overlaps the fire at origin
        self.assertIn("Want me to delete it?", notes)
        self.assertIn("default 'Light'", notes)

    def test_far_away_cube_is_mentioned_without_overlap_claim(self):
        skill, _ = build_skill(objects=[FakeObject(name="Cube", location=[30.0, 30.0, 0.0])], with_scene=True)
        result = skill.execute({"camp_name": "C"})
        self.assertIn("default 'Cube'", result.data["notes"][0])
        self.assertNotIn("campfire", result.data["notes"][0])

    def test_clear_defaults_deletes_them_when_user_asked(self):
        skill, bridge = build_skill(objects=self._defaults(), with_scene=True)

        result = skill.execute({"camp_name": "C", "clear_defaults": True})

        self.assertTrue(result.success, result.error)
        self.assertIsNone(bridge.get_object("Cube"))
        self.assertIsNone(bridge.get_object("Light"))
        self.assertEqual(result.data["leftover_defaults"], [])
        self.assertTrue(any("Deleted the leftover default 'Cube'" in n for n in result.data["notes"]))

    def test_user_objects_with_similar_names_are_never_touched(self):
        mine = [FakeObject(name="Cube_Big"), FakeObject(name="MyCube"), FakeObject(name="Light_Key", type_="LIGHT"),
                FakeObject(name="Cube", type_="CAMERA")]  # wrong type for a default Cube
        skill, bridge = build_skill(objects=mine, with_scene=True)

        result = skill.execute({"camp_name": "C", "clear_defaults": True})

        self.assertTrue(result.success)
        self.assertNotIn("notes", result.data)
        for obj in mine:
            self.assertIsNotNone(bridge.get_object(obj.name), obj.name)

    def test_clean_scene_has_no_notes(self):
        skill, _ = build_skill(with_scene=True)
        result = skill.execute({"camp_name": "C"})
        self.assertNotIn("notes", result.data)

    def test_works_when_scene_inspect_is_not_available(self):
        skill, _ = build_skill(objects=self._defaults(), with_scene=False)
        result = skill.execute({"camp_name": "C"})
        self.assertTrue(result.success, result.error)
        self.assertNotIn("notes", result.data)

    def test_clear_defaults_must_be_boolean(self):
        skill, _ = build_skill(with_scene=True)
        result = skill.execute({"clear_defaults": "yes please"})
        self.assertFalse(result.success)


class TestCampsiteFailures(unittest.TestCase):

    def test_invalid_options_return_failure_not_exception(self):
        skill, _ = build_skill()
        for ctx in ({"tree_count": 99}, {"tree_count": -1}, {"rock_count": 50},
                    {"location": [1, 2]}, {"camp_name": ""}, {"seed": "x"}):
            result = skill.execute(ctx)
            self.assertFalse(result.success, ctx)
            self.assertIn("Invalid campsite options", result.error)

    def test_missing_tool_fails_cleanly_with_progress(self):
        skill, _ = build_skill(skip_tools=("light.create",))
        result = skill.execute({})
        self.assertFalse(result.success)
        self.assertIn("light.create", result.error)
        self.assertTrue(len(result.steps_completed) > 10)  # scene was already built before it failed

    def test_required_permissions_list_new_tools(self):
        skill, _ = build_skill()
        perms = skill.required_permissions(None)
        for tool in ("light.create", "world.set", "material.modify", "scene.inspect", "object.delete"):
            self.assertIn(tool, perms)


if __name__ == "__main__":
    unittest.main()
