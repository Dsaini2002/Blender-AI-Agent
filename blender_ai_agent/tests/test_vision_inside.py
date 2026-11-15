"""The badminton hall check renders showed only the outside of the walls and roof, so the reviewer said
'everything is missing' every round (log 20261114_165852)."""

from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent import self_correct as sc
from blender_ai_agent.tools.render_views import camera_pose, occluders


def box(x0, y0, z0, x1, y1, z1):
    return {"min": [x0, y0, z0], "max": [x1, y1, z1]}


HALL = {
    "wooden_floor": box(-9.7, -6.05, 0, 9.7, 6.05, 0),
    "wall_back": box(-10, 6.05, 0, 10, 6.65, 7),
    "wall_front": box(-10, -6.65, 0, 10, -6.05, 7),
    "wall_right": box(9.7, -6.05, 0, 10.3, 6.05, 7),
    "wall_left": box(-10.3, -6.05, 0, -9.7, 6.05, 7),
    "roof": box(-10, -6.35, 7, 10, 6.35, 7),
    "badminton_net_net": box(-0.01, -3.0, 0.79, 0.01, 3.0, 1.55),
    "stand": box(-4, -5.5, 0, 4, -3.6, 2.5),
}
LO, HI = [-10.3, -6.65, 0.0], [10.3, 6.65, 7.0]


class TestOccluders(unittest.TestCase):

    def test_front_view_hides_roof_and_front_wall_only(self):
        cam = camera_pose(LO, HI, "front")["location"]
        hidden = occluders(HALL, LO, HI, cam)
        self.assertEqual(hidden, {"roof", "wall_front"})

    def test_three_quarter_view_hides_the_two_near_walls(self):
        cam = camera_pose(LO, HI, "three_quarter")["location"]        # from +x, -y, above
        hidden = occluders(HALL, LO, HI, cam)
        self.assertEqual(hidden, {"roof", "wall_front", "wall_right"})

    def test_court_items_are_never_hidden(self):
        for view in ("front", "three_quarter", "right", "top"):
            hidden = occluders(HALL, LO, HI, camera_pose(LO, HI, view)["location"])
            self.assertFalse({"badminton_net_net", "stand", "wooden_floor", "wall_back"} & hidden, view)

    def test_unnamed_ceiling_slab_is_found(self):
        boxes = dict(HALL)
        boxes.pop("roof")
        boxes["slab_top"] = box(-10, -6.35, 7, 10, 6.35, 7.2)
        hidden = occluders(boxes, LO, HI, camera_pose(LO, HI, "front")["location"])
        self.assertIn("slab_top", hidden)

    def test_open_scene_hides_nothing(self):
        park = {"tree": box(0, 0, 0, 2, 2, 6), "bench": box(3, 0, 0, 5, 0.6, 0.9), "ground": box(-10, -10, 0, 10, 10, 0)}
        self.assertEqual(occluders(park, [-10, -10, 0], [10, 10, 6], camera_pose([-10, -10, 0], [10, 10, 6], "front")["location"]), set())


class TestReviewerIsTold(unittest.TestCase):

    def test_note_reaches_the_reviewer(self):
        seen = {}

        def generate(system, parts, **kw):
            seen["text"] = " ".join(p.get("text", "") for p in parts)
            return '{"score": 9, "problems": []}'

        sc.critique_renders(generate, "make a hall", [], note="roofs are hidden on purpose")
        self.assertIn("NOTE: roofs are hidden on purpose", seen["text"])


if __name__ == "__main__":
    unittest.main()
