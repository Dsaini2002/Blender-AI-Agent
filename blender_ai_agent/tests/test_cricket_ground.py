"""'create a cricket ground with wickets, and boundary, and with stadium light' (log 20261114_144321)
was sent to build.iterate (a one-object script builder) instead of the team planner, the wicket's
bails sat half-way down the stumps and the light masts leaned. Also 'please fix this, this is not a
cricket ground' went to build.iterate and rebuilt from scratch."""

from . import _bpy_stub  # noqa: F401

import math
import unittest
from types import SimpleNamespace

from blender_ai_agent.multi_agent.team import is_big_request
from blender_ai_agent.skills.builtins.iterative_build import IterativeBuildSkill
from blender_ai_agent.tools import paths
from blender_ai_agent.tools.library_tools import LibraryPlaceTool, load_library, yaw_to_face
from .test_library_recipes import NodeBridge, _ensure_lights

_ensure_lights(NodeBridge)


class LightBridge(NodeBridge):
    def create_light(self, name, light_type="POINT", location=None, rotation=None, color=None, energy=1000.0,
                     size=0.25, spot_angle=45.0):
        from .fakes import FakeObject
        obj = FakeObject(name=name, type_="LIGHT", location=list(location or [0, 0, 0]), rotation=list(rotation or [0, 0, 0]))
        obj.light = {"type": light_type, "energy": energy, "spot_angle": spot_angle}
        self._objects.append(obj)
        return obj


class TestRouting(unittest.TestCase):

    def skill(self):
        return IterativeBuildSkill(tool_caller=None, config_loader=lambda: SimpleNamespace(api_key="k"))

    def test_sports_grounds_are_scenes(self):
        for text in ("create a cricket ground with wickets, and boundary, and with stadium light",
                     "make a football field", "tennis court at night", "build a water park", "a race track"):
            self.assertTrue(is_big_request(text), text)

    def test_scenes_and_fixes_never_go_to_the_one_object_builder(self):
        skill = self.skill()
        for text in ("create a cricket ground with wickets, and boundary, and with stadium light",
                     "please fix this, this is not a cricket ground",
                     "make the stadium better", "improve the park"):
            self.assertEqual(skill.can_handle(text), 0.0, text)

    def test_a_ground_plane_alone_is_not_a_scene(self):
        self.assertFalse(is_big_request("put a cube on the ground"))


class TestCricketModels(unittest.TestCase):

    def setUp(self):
        paths.clear()

    def test_wicket_has_three_stumps_and_bails_on_top(self):
        spec = load_library()["cricket_wicket"]
        stumps = [p for p in spec["parts"] if p["name"].startswith("stump")]
        bails = [p for p in spec["parts"] if p["name"].startswith("bail")]
        self.assertEqual((len(stumps), len(bails)), (3, 2))
        stump_top = max(p["offset"][2] + p["scale"][2] for p in stumps)
        self.assertAlmostEqual(stump_top, 0.711, places=3)
        for bail in bails:                                   # resting on the stump tops, not half-way down
            self.assertGreaterEqual(bail["offset"][2], stump_top)
            self.assertLess(bail["offset"][2] - stump_top, 0.02)
        width = max(p["offset"][0] for p in stumps) - min(p["offset"][0] for p in stumps) + 2 * stumps[0]["scale"][0]
        self.assertAlmostEqual(width, 0.2286, places=2)

    def test_wicket_places(self):
        result = LibraryPlaceTool(LightBridge()).execute({"model": "wickets", "location": [0, 10.06, 0]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["model"], "cricket_wicket")

    def test_stadium_light_is_upright_and_aimed_at_the_field(self):
        bridge = LightBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "floodlight", "location": [0, -60, 0], "face_towards": [0, 0]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["model"], "stadium_light")
        mast = bridge.get_object("stadium_light_mast")
        self.assertEqual(list(mast.rotation_euler[:2]), [0, 0])            # straight up, not leaning
        light = bridge.get_object(result.data["lights"][0])
        self.assertEqual(light.light["type"], "SPOT")
        self.assertGreater(light.light["spot_angle"], 45)
        rx, _, rz = light.rotation_euler                                  # spot shines along R_z(rz) R_x(rx) (0,0,-1)
        direction = (-math.sin(rz) * math.sin(rx), math.cos(rz) * math.sin(rx), -math.cos(rx))
        self.assertGreater(direction[1], 0.7)                             # towards the field centre (+Y from y=-60)
        self.assertLess(direction[2], -0.2)                               # and down onto it
        self.assertAlmostEqual(result.data["size_m"][2], 21.6, places=1)

    def test_face_towards_turns_any_side(self):
        bridge = LightBridge()
        for loc in ([60, 0, 0], [-60, 0, 0], [0, 60, 0]):
            result = LibraryPlaceTool(bridge).execute({"model": "stadium_light", "location": loc,
                                                       "face_towards": [0, 0], "prefix": f"l{loc[0]}_{loc[1]}_"})
            yaw = math.radians(result.data["yaw_degrees"])
            front = (-math.sin(yaw), math.cos(yaw))                       # +Y front after the turn
            to_centre = (-loc[0] / 60.0, -loc[1] / 60.0)
            self.assertAlmostEqual(front[0], to_centre[0], places=4)
            self.assertAlmostEqual(front[1], to_centre[1], places=4)

    def test_yaw_to_face(self):
        self.assertAlmostEqual(yaw_to_face([0, 1], [0, 1]), 0.0)
        self.assertAlmostEqual(yaw_to_face([0, -1], [1, 0]) % 360, 90.0)


if __name__ == "__main__":
    unittest.main()
