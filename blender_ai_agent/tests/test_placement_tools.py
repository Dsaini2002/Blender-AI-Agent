from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tests.fakes_ext import FakeBridge
from blender_ai_agent.tools.placement_tools import (
    MeasureObjectsTool, PlaceNextToTool, PlaceOnTool, SnapToGroundTool, delta_next_to, delta_on_top,
)


def obj(name, location, bbox):
    o = FakeObject(name=name, location=list(location))
    o.fake_bbox = {"min": list(bbox[0]), "max": list(bbox[1])}
    return o


class TestPlacementMath(unittest.TestCase):

    def test_on_top_centres_and_touches(self):
        delta = delta_on_top({"min": [0, 0, 5], "max": [1, 1, 6]}, {"min": [-1, -1, 0], "max": [1, 1, 1]})
        self.assertEqual(delta, [-0.5, -0.5, -4.0])

    def test_next_to_touches_on_the_requested_side(self):
        target = {"min": [0, 0, 0], "max": [2, 2, 1]}
        right = delta_next_to({"min": [0, 0, 3], "max": [1, 1, 4]}, target, "right")
        self.assertEqual(right, [2.0, 0.5, -3.0])
        front = delta_next_to({"min": [0, 0, 0], "max": [1, 1, 1]}, target, "front", gap=0.5)
        self.assertEqual(front, [0.5, -1.5, 0.0])


class TestPlacementTools(unittest.TestCase):

    def setUp(self):
        self.bridge = FakeBridge(objects=[
            obj("Table", [0, 0, 0], ([-1, -0.5, 0], [1, 0.5, 0.8])),
            obj("Book", [3, 3, 2], ([-0.1, -0.15, 0], [0.1, 0.15, 0.05])),
            obj("Chair", [5, 5, 0.3], ([-0.25, -0.25, 0], [0.25, 0.25, 0.9])),
        ])

    def test_place_on_puts_book_on_table_top(self):
        result = PlaceOnTool(self.bridge).execute({"name": "Book", "target": "Table"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(self.bridge.get_object("Book").location, [0.0, 0.0, 0.8])
        self.assertAlmostEqual(result.data["box"]["min"][2], 0.8)

    def test_place_on_offset(self):
        PlaceOnTool(self.bridge).execute({"name": "Book", "target": "Table", "offset": [0.5, -0.2]})
        self.assertEqual(self.bridge.get_object("Book").location, [0.5, -0.2, 0.8])

    def test_place_next_to_stands_on_same_floor(self):
        result = PlaceNextToTool(self.bridge).execute({"name": "Chair", "target": "Table", "side": "front", "gap": 0.1})
        self.assertTrue(result.success, result.error)
        self.assertEqual(self.bridge.get_object("Chair").location, [0.0, -0.85, 0.0])

    def test_bad_side_and_missing_object_fail_cleanly(self):
        self.assertFalse(PlaceNextToTool(self.bridge).execute({"name": "Chair", "target": "Table", "side": "up"}).success)
        missing = PlaceOnTool(self.bridge).execute({"name": "Ghost", "target": "Table"})
        self.assertFalse(missing.success)
        self.assertIn("Ghost", missing.error)

    def test_snap_to_ground_and_onto_a_floor_object(self):
        result = SnapToGroundTool(self.bridge).execute({"names": ["Book", "Chair"]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(self.bridge.get_object("Book").location[2], 0.0)
        self.assertEqual(self.bridge.get_object("Chair").location[2], 0.0)
        result = SnapToGroundTool(self.bridge).execute({"names": "Chair", "ground": "Table"})
        self.assertEqual(self.bridge.get_object("Chair").location[2], 0.8)

    def test_measure_reports_boxes_and_combined(self):
        result = MeasureObjectsTool(self.bridge).execute({"names": ["Table", "Book", "Nope"]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["objects"]["Table"]["size"], [2.0, 1.0, 0.8])
        self.assertIn("combined", result.data)
        self.assertEqual(result.data["not_found"], ["Nope"])


if __name__ == "__main__":
    unittest.main()
