from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.scene_checks import geometry_problems
from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tests.fakes_ext import FakeBridge
from blender_ai_agent.tools.placement_tools import SnapToGroundTool, connected_groups


def part(name, z, box):
    o = FakeObject(name=name, location=[0.0, 2.0, z])
    o.fake_bbox = {"min": list(box[0]), "max": list(box[1])}
    o.material_name = "m"
    return o


def floating_pine(z=3.0):
    """A library pine tree placed 3 m too high: trunk 0-1.2, tiers stacked on it (like the user's log)."""
    return [part("pine_tree_trunk", z, ((-0.2, -0.2, 0.0), (0.2, 0.2, 1.2))),
            part("pine_tree_tier1", z, ((-1.5, -1.5, 1.0), (1.5, 1.5, 2.6))),
            part("pine_tree_tier2", z, ((-1.1, -1.1, 2.3), (1.1, 1.1, 3.7))),
            part("pine_tree_tier3", z, ((-0.7, -0.7, 3.4), (0.7, 0.7, 5.0)))]


class TestGroupedGrounding(unittest.TestCase):

    def test_snapping_moves_a_multi_part_model_as_one_piece(self):
        bridge = FakeBridge(objects=floating_pine())
        names = [o.name for o in bridge.get_objects()]
        result = SnapToGroundTool(bridge).execute({"names": names})
        self.assertTrue(result.success, result.error)
        zs = {n: bridge.get_object(n).location[2] for n in names}
        self.assertEqual(set(zs.values()), {0.0})                   # all moved by the same amount
        self.assertEqual(bridge.measure_objects(["pine_tree_tier3"])["max"][2], 5.0)   # crown still on top

    def test_floating_model_is_reported_once_with_all_its_parts(self):
        bridge = FakeBridge(objects=floating_pine())
        problems = geometry_problems(bridge, [o.name for o in bridge.get_objects()])
        self.assertEqual(len(problems), 1)
        self.assertIn("+3 parts", problems[0]["where"])
        self.assertIn("pine_tree_tier3", problems[0]["fix"])

    def test_model_on_the_ground_is_fine(self):
        bridge = FakeBridge(objects=floating_pine(z=0.0))
        self.assertEqual(geometry_problems(bridge, [o.name for o in bridge.get_objects()]), [])

    def test_separate_objects_are_separate_groups(self):
        boxes = {"a": {"min": [0, 0, 0], "max": [1, 1, 1]}, "b": {"min": [0, 0, 1], "max": [1, 1, 2]},
                 "c": {"min": [5, 5, 0], "max": [6, 6, 1]}}
        self.assertEqual(sorted(sorted(g) for g in connected_groups(boxes)), [["a", "b"], ["c"]])


if __name__ == "__main__":
    unittest.main()


class TestLibraryPlaceSettles(unittest.TestCase):

    def test_tree_placed_in_the_air_drops_to_the_ground_but_lamp_on_table_stays(self):
        from blender_ai_agent.tools.library_tools import LibraryPlaceTool
        bridge = FakeBridge()
        result = LibraryPlaceTool(bridge).execute({"model": "pine_tree", "location": [0, 2, 3.0]})
        self.assertTrue(result.success, result.error)
        self.assertGreater(result.data["dropped_to_ground_m"], 2.9)
        self.assertAlmostEqual(bridge.measure_objects(result.data["meshes"])["min"][2], 0.0, places=4)

        table = FakeObject(name="table", location=[10.0, 0.0, 0.0])
        table.fake_bbox = {"min": [-1, -1, 0], "max": [1, 1, 0.75]}
        bridge = FakeBridge(objects=[table])
        result = LibraryPlaceTool(bridge).execute({"model": "lantern", "location": [10, 0, 0.75]})
        self.assertIsNone(result.data["dropped_to_ground_m"])
