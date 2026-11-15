"""Room screenshot (23:05): a desk stood inside a bookshelf and a wardrobe inside the other bookshelf, and nothing
reported it - the geometry check had no 'two things in the same space' test."""

from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.scene_checks import _clash_problems, geometry_problems, library_items
from blender_ai_agent.tools.edit_tools import MoveByTool
from blender_ai_agent.tools.library_tools import LibraryPlaceTool
from .test_hostel_campus import Bridge


def place(bridge, model, location, **extra):
    result = LibraryPlaceTool(bridge).execute({"model": model, "location": location, **extra})
    assert result.success, result.error
    return result


def clashes(bridge):
    return [p for p in geometry_problems(bridge, [o.name for o in bridge.get_objects()])
            if "inside" in p["issue"] or "into the wall" in p["issue"]]


class TestClashes(unittest.TestCase):

    def test_desk_inside_bookshelf_is_found_and_the_fix_works(self):
        bridge = Bridge()
        place(bridge, "bookshelf", [0, 2.45, 0])
        place(bridge, "study_table", [0, 2.35, 0])
        found = clashes(bridge)
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["where"], "study_table")
        self.assertIn("object.move_by(names=['study_table']", found[0]["fix"])
        offset = eval(found[0]["fix"].split("offset=")[1].split(")")[0])
        self.assertTrue(MoveByTool(bridge).execute({"names": ["study_table"], "offset": offset}).success)
        self.assertEqual(clashes(bridge), [])

    def test_second_copy_is_its_own_item(self):
        bridge = Bridge()
        place(bridge, "bookshelf", [0, 0, 0])
        place(bridge, "bookshelf", [5, 0, 0])
        place(bridge, "wardrobe", [5, 0.1, 0])
        items = library_items([o.name for o in bridge.get_objects()])
        self.assertIn("bookshelf.001", items)
        found = clashes(bridge)
        self.assertEqual([p["where"] for p in found], ["wardrobe"])
        self.assertIn("'bookshelf.001'", found[0]["issue"])

    def test_normal_rooms_are_not_flagged(self):
        # real sizes (as Blender measures them): bed with nightstands beside it, a lamp ON a nightstand, a rug under
        # the bed, a chair tucked under the desk, a chandelier above
        boxes = {
            "double_bed_frame": box(-0.95, 0.95, 0.5, 2.7, 0, 1.28),
            "nightstand_body": box(-1.55, -1.05, 2.14, 2.56, 0, 0.58),
            "table_lamp_shade": box(-1.46, -1.14, 2.19, 2.51, 0.58, 1.13),
            "rug_field": box(-1.3, 1.3, -0.3, 1.5, 0, 0.016),
            "study_table_desk": box(-2.6, -1.4, -1.8, -1.2, 0, 0.76),
            "chair_chair": box(-2.22, -1.78, -1.52, -1.08, 0, 0.92),
            "chandelier_ring": box(-0.47, 0.47, -0.47, 0.47, 2.15, 3.0),
        }
        self.assertEqual(_clash_problems(sorted(boxes), boxes), [])

    def test_furniture_in_a_wall_is_pushed_into_the_room(self):
        boxes = {"room_wall_right": box(2.7, 3.0, -3, 3, 0, 3), "sofa_sofa": box(-1, 1, -0.4, 0.4, 0, 0.85),
                 "tv_unit_cabinet": box(2.67, 3.13, -2.5, -0.7, 0, 0.5)}
        found = _clash_problems(sorted(boxes), boxes)
        self.assertEqual([p["where"] for p in found], ["tv_unit"])
        offset = eval(found[0]["fix"].split("offset=")[1].split(")")[0])
        self.assertLess(offset[0], 0)                              # towards the room, not out through the wall


def box(x0, x1, y0, y1, z0, z1):
    return {"min": [x0, y0, z0], "max": [x1, y1, z1]}


class TestMoveBy(unittest.TestCase):

    def test_moves_every_part_together(self):
        bridge = Bridge()
        place(bridge, "wardrobe", [1, 1, 0])
        before = {o.name: list(o.location) for o in bridge.get_objects()}
        result = MoveByTool(bridge).execute({"names": ["wardrobe"], "offset": [-0.4, 0, 0]})
        self.assertTrue(result.success, result.error)
        self.assertEqual(sorted(result.data["moved"]), sorted(before))
        for o in bridge.get_objects():
            self.assertAlmostEqual(o.location[0], before[o.name][0] - 0.4)

    def test_bad_input(self):
        bridge = Bridge()
        self.assertFalse(MoveByTool(bridge).execute({"names": ["ghost"], "offset": [1, 0, 0]}).success)
        self.assertFalse(MoveByTool(bridge).execute({"names": ["x"], "offset": "left"}).success)


if __name__ == "__main__":
    unittest.main()
