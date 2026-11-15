"""Error finder (diagnostics/scene_audit.py): the study room the vision reviewer had to catch alone - desk inside the
bookshelf under a custom prefix, shelves in the walls, floating plant, stacked lights, whiteboard in mid-air."""

from . import _bpy_stub  # noqa: F401

import os
import tempfile
import unittest
from types import SimpleNamespace

from blender_ai_agent.diagnostics import scene_audit as sa


def obj(name, lo, hi, kind="MESH", mats=("m",), view=1.0, **extra):
    entry = {"name": name, "type": kind, "location": [(a + b) / 2 for a, b in zip(lo, hi)], "rotation": [0, 0, 0],
             "scale": [1, 1, 1], "hidden": False, "materials": list(mats), "in_view": view,
             "box": {"min": list(lo), "max": list(hi)}}
    entry.update(extra)
    return entry


def light(name, loc, energy=300):
    return {"name": name, "type": "LIGHT", "location": list(loc), "rotation": [0, 0, 0], "scale": [1, 1, 1],
            "hidden": False, "materials": [], "box": None, "in_view": None,
            "light": {"type": "POINT", "energy": energy, "color": [1, 1, 1]}}


def room(*extra, camera="Camera"):
    objects = [
        obj("room_floor", [-2.5, -2, -0.1], [2.5, 2, 0]),
        obj("room_wall_back", [-2.5, 1.9, 0], [2.5, 2.1, 3]),
        obj("room_wall_left", [-2.6, -2, 0], [-2.4, 2, 3]),
        obj("room_wall_right", [2.4, -2, 0], [2.6, 2, 3]),
        {"name": "Camera", "type": "CAMERA", "location": [0, -7, 4], "rotation": [1.2, 0, 0], "scale": [1, 1, 1],
         "hidden": False, "materials": [], "box": None, "in_view": None},
        light("led0", [-1, 0, 2.8]), light("led1", [1, 0, 2.8]),
    ] + list(extra)
    return {"objects": objects, "camera": camera, "engine": "CYCLES", "collections": {"Collection": len(objects)}}


def kinds(findings):
    return [f["kind"] for f in findings]


LIBRARY = {"study_table": ["desk"], "bookshelf": ["shelf", "books"], "chair": ["chair"],
           "bush": ["blob1", "blob2", "blob3"], "double_bed": ["frame", "headboard"]}


class ErrorFinderTest(unittest.TestCase):

    def setUp(self):
        self._old = sa._library_parts
        sa._library_parts = lambda: LIBRARY

    def tearDown(self):
        sa._library_parts = self._old

    def test_clean_room_has_no_errors(self):
        snap = room(obj("study_desk_desk", [-0.6, 0.9, 0], [0.6, 1.5, 0.76]),
                    obj("study_chair_chair", [-0.22, 0.6, 0], [0.22, 1.04, 0.92]),
                    obj("whiteboard", [-0.8, 1.86, 1.5], [0.8, 1.9, 2.3]))
        self.assertEqual(sa.find_errors(snap, "a study room with a desk, chair and whiteboard"), [])

    def test_custom_prefix_desk_inside_bookshelf_is_found(self):
        snap = room(obj("study_desk_desk", [-0.6, 1.2, 0], [0.6, 1.8, 0.76]),
                    obj("bookshelf_shelf", [-1, 1.5, 0], [1, 1.88, 2]),
                    obj("bookshelf_books", [-0.95, 1.55, 0.03], [0.93, 1.85, 1.9]))
        found = [f for f in sa.find_errors(snap) if f["kind"] == "OVERLAP"]
        self.assertEqual(len(found), 1, found)
        self.assertEqual(set(found[0]["objects"]), {"study_desk", "bookshelf"})
        self.assertEqual(found[0]["severity"], "high")
        self.assertIn("move_by", found[0]["fix"])

    def test_books_in_their_shelf_and_chair_under_desk_are_fine(self):
        snap = room(obj("bookshelf_shelf", [-1, 1.4, 0], [1, 1.85, 2]),
                    obj("bookshelf_books", [-0.95, 1.45, 0.03], [0.93, 1.8, 1.9]),
                    obj("desk", [1.0, -1.0, 0], [2.2, -0.4, 0.76]),
                    obj("chair", [1.4, -0.9, 0], [1.8, -0.5, 0.9]))
        self.assertNotIn("OVERLAP", kinds(sa.find_errors(snap)))

    def test_through_wall_floating_sunk(self):
        snap = room(obj("bookshelf_shelf", [-2.5, -1, 0], [-1.6, 1, 2]),
                    obj("indoor_plant_blob1", [-1, -1, 0.4], [-0.5, -0.5, 1.0]),
                    obj("indoor_plant_blob2", [-0.9, -0.9, 0.45], [-0.6, -0.6, 0.9]),
                    obj("sofa", [0.5, -1.5, -0.2], [2.0, -0.6, 0.7]))
        found = sa.find_errors(snap)
        self.assertIn("THROUGH WALL", kinds(found))
        wall = next(f for f in found if f["kind"] == "THROUGH WALL")
        self.assertGreater(wall["fix"].count("0."), 0)
        self.assertIn("[0.", wall["fix"].replace("-", ""))
        floating = next(f for f in found if f["kind"] == "FLOATING")
        self.assertEqual(floating["objects"], ["indoor_plant"])
        self.assertAlmostEqual(floating["numbers"]["gap_m"], 0.4, places=2)
        self.assertIn("SUNK", kinds(found))

    def test_lights_camera_material_default_cube(self):
        snap = room(obj("Cube", [5, 5, 0], [7, 7, 2], mats=(), view=0.0),
                    obj("desk", [-0.6, 0.9, 0], [0.6, 1.5, 0.76]), obj("chair", [1.4, -0.9, 0], [1.8, -0.5, 0.9]),
                    light("led2", [0, 0, 3]), light("led3", [0, 0, 3]), light("led4", [1, 1, 2], energy=0))
        found = sa.find_errors(snap)
        text = " | ".join(f["what"] for f in found)
        self.assertIn("same spot", text)
        self.assertIn("no energy", text)
        self.assertIn("outside the camera view", text)
        self.assertIn("default Blender primitive", text)
        self.assertIn("no material", text)
        self.assertIn("OUTSIDE ROOM", kinds(found))

    def test_no_camera_and_inactive_camera(self):
        snap = room()
        snap["objects"] = [o for o in snap["objects"] if o["type"] != "CAMERA"]
        self.assertIn("there is no camera", [f["what"] for f in sa.find_errors(snap)])
        self.assertIn("no camera is active", [f["what"] for f in sa.find_errors(room(camera=""))])

    def test_whiteboard_in_mid_air(self):
        found = sa.find_errors(room(obj("whiteboard", [-0.05, -0.8, 1], [0.05, 0.8, 2])))
        self.assertEqual([f["kind"] for f in found], ["NOT ON WALL"])

    def test_request_words_and_collections(self):
        snap = room(obj("desk", [-0.6, 0.9, 0], [0.6, 1.5, 0.76]))
        found = sa.find_errors(snap, "Add a desk, a large glass window and a plant.\n"
                                     "Organize objects into collections: Room, Furniture")
        missing = next(f for f in found if f["kind"] == "MISSING?")
        self.assertIn("window", missing["objects"])
        self.assertIn("plant", missing["objects"])
        self.assertNotIn("desk", missing["objects"])
        cols = next(f for f in found if f["kind"] == "COLLECTIONS")
        self.assertEqual(cols["objects"], ["Room", "Furniture"])

    def test_scale_size_tilt_duplicate_console(self):
        snap = room(obj("flat_thing", [0, 0, 0], [1, 1, 0.5], scale=[1, 0, 1]),
                    obj("chair", [-1, -1, 0], [-0.6, -0.6, 4.5]),
                    obj("table", [1, -1.5, 0], [2, -0.8, 0.75], rotation=[0.3, 0, 0]),
                    obj("lamp_a", [-1.5, 0.5, 0], [-1.3, 0.7, 1.5]), obj("lamp_b", [-1.5, 0.5, 0], [-1.3, 0.7, 1.5]))
        found = sa.find_errors(snap, console="Traceback (most recent call last)\nNameError: x")
        for kind in ("SCALE", "SIZE", "TILTED", "DUPLICATE", "CONSOLE"):
            self.assertIn(kind, kinds(found), kind)

    def test_report_text_and_files(self):
        snap = room(obj("Cube", [5, 5, 0], [7, 7, 2], mats=()))
        bridge = SimpleNamespace(scene_snapshot=lambda: snap)
        with tempfile.TemporaryDirectory() as folder:
            path = sa.write_errors(bridge, "make a room", "", folder)
            self.assertEqual(os.path.basename(path), "errors.txt")
            self.assertTrue(os.path.isfile(os.path.join(folder, "errors.json")))
            text = open(path, encoding="utf-8").read()
        self.assertIn("ERROR FINDER", text)
        self.assertIn("problem(s):", text)
        self.assertIn("why:", text)
        self.assertIn("fix:", text)
        self.assertIn("EVERY OBJECT", text)
        self.assertIn("room_wall_back | MESH", text)

    def test_a_broken_check_does_not_hide_the_others(self):
        snap = room(obj("Cube", [5, 5, 0], [7, 7, 2], mats=()))
        finder = sa.Finder(snap)
        finder.check_tilt = lambda: (_ for _ in ()).throw(KeyError("x"))
        found = finder.run()
        self.assertIn("FINDER", kinds(found))
        self.assertIn("DEFAULT", kinds(found))


class UserTestRunsTest(unittest.TestCase):
    """What the 3 test prompts of 15 Nov showed the first version missed or said wrong."""

    def setUp(self):
        self._old = sa._library_parts
        sa._library_parts = lambda: LIBRARY

    def tearDown(self):
        sa._library_parts = self._old

    def test_bed_through_the_wall_reports_the_real_depth(self):
        found = sa.find_errors(room(obj("double_bed_frame", [-0.95, 0.45, 0], [0.95, 2.55, 0.38]),
                                    obj("double_bed_headboard", [-1, 2.47, 0], [1, 2.57, 1.28])))
        wall = next(f for f in found if f["kind"] == "THROUGH WALL")
        self.assertIn("goes 0.67 m into", wall["what"])
        self.assertIn("OTHER side", wall["what"])

    def test_desk_placed_at_its_own_height_floats_with_a_reason(self):
        found = sa.find_errors(room(obj("study_table_desk", [-0.6, 1.2, 0.75], [0.6, 1.8, 1.51])))
        floating = next(f for f in found if f["kind"] == "FLOATING")
        self.assertIn("TOP height", floating["why"])

    def test_startup_light_and_camera_left_over(self):
        snap = room(light("Light", [4.08, 1.01, 5.9], 1000))
        snap["objects"][4]["location"] = [7.36, -6.93, 4.96]
        found = sa.find_errors(snap, "a room with a camera outside the open front")
        text = " | ".join(f["what"] for f in found)
        self.assertIn("start-up light", text)
        self.assertIn("start position", text)

    def test_generic_prism_names_window_by_material_and_wall_by_shape(self):
        snap = room(obj("prism_object", [-2.5, -1, 0.75], [-2.49, 1, 2.25], mats=("window_glass",)))
        found = sa.find_errors(snap, "add a large glass window")
        self.assertNotIn("FLOATING", kinds(found))           # glass in the wall hangs there
        self.assertNotIn("MISSING?", kinds(found))           # its material says window
        self.assertIn("looks like a window", next(f for f in found if f["kind"] == "NAME")["what"])

    def test_startup_cube_scaled_into_a_room_swallows_everything(self):
        snap = room(camera="Camera")
        snap["objects"] = [o for o in snap["objects"] if not o["name"].startswith("room_")] + [
            obj("Cube", [-2, -2, -1.5], [2, 2, 1.5], mats=("Material",)),
            obj("prism_object", [-2.1, -2, 1.5], [-1.9, 2, 4.5], mats=()),
            obj("wall_back_plus_y", [-0.5, 1.5, 1.5], [0.5, 2.5, 4.5]),
            obj("sofa", [-1.5, -1, 0.75], [-0.6, 1, 1.6]), obj("desk", [-0.6, -1.9, 0.75], [0.6, -1.3, 1.51]),
            obj("bookshelf", [-0.6, -1.9, 0.75], [0.6, -1.3, 1.51]), obj("whiteboard", [-1, -1, 0.2], [1, 1, 2.2])]
        found = sa.find_errors(snap, "a room with 3 walls and a floor")
        swallow = [f for f in found if f["kind"] == "OVERLAP" and "block" in f["what"]]
        self.assertEqual(len(swallow), 1)
        self.assertEqual(swallow[0]["objects"][0], "Cube")
        self.assertFalse(any(f["kind"] == "OVERLAP" and "Cube" in f["objects"] and f is not swallow[0] for f in found))
        self.assertIn("pillar", " ".join(f["what"] for f in found))
        self.assertIn("starts 1.50 m above the floor", " ".join(f["what"] for f in found))
        self.assertIn("2 x 2 x 2 m start cube", " ".join(f["what"] for f in found))
        self.assertIn("DUPLICATE", kinds(found))
        self.assertFalse(any(f["kind"] == "OVERLAP" and set(f["objects"]) == {"desk", "bookshelf"} for f in found))
        self.assertIn("floor", next(f for f in found if f["kind"] == "MISSING?")["objects"])

    def test_floor_centred_on_zero_is_one_finding(self):
        snap = room(obj("chair", [-1, -1, 0], [-0.6, -0.6, 0.9]), obj("desk", [0, 0, 0], [1.2, 0.6, 0.76]),
                    obj("sofa", [1, -1.5, 0], [2.2, -0.7, 0.8]))
        snap["objects"][0]["box"] = {"min": [-2.5, -2, -0.05], "max": [2.5, 2, 0.05]}
        sunk = [f for f in sa.find_errors(snap) if f["kind"] == "SUNK"]
        self.assertEqual(len(sunk), 1)
        self.assertIn("move the floor down", sunk[0]["fix"])


class OutdoorTest(unittest.TestCase):

    def test_building_joined_per_material_is_one_thing(self):
        snap = room()
        snap["objects"] = [o for o in snap["objects"] if not o["name"].startswith("room_")] + [
            obj("campus_ground", [-70, -70, 0], [70, 70, 0]),
            obj("hostel_brick", [-25, -25, 0], [25, 25, 19]), obj("hostel_glass", [-25, -25, 0.1], [25, 25, 18]),
            obj("hostel_doors", [-17, -25, 0.15], [17, 24, 18]), obj("hostel_tt_tables", [10, -22, 0.88], [22, -20, 0.91]),
            obj("campus_wall_n", [-60, 59.9, 0], [60, 60.1, 2]), obj("campus_wall_s", [-60, -60.1, 0], [60, -59.9, 2]),
            obj("bicycle_parking_frame", [30, 0, 0], [39, 3, 2.5]),
            obj("court_pole", [24.8, 0, 0], [25.1, 0.2, 3.5])]
        found = sa.find_errors(snap)
        self.assertEqual([(f["kind"], f["objects"]) for f in found], [("OVERLAP", ["court_pole", "hostel"])])


class WiringTest(unittest.TestCase):

    def test_check_round_writes_errors_txt(self):
        source = open(os.path.join(os.path.dirname(sa.__file__), "..", "agent", "post_verify.py")).read()
        self.assertIn("write_errors(self.bridge, request, facts.console_text, report.folder)", source)

    def test_panel_has_find_errors_button(self):
        from blender_ai_agent.ui import panel
        self.assertEqual(panel.AIAGENT_OT_find_errors.bl_idname, "aiagent.find_errors")
        import blender_ai_agent
        self.assertIn(panel.AIAGENT_OT_find_errors, blender_ai_agent.classes)


if __name__ == "__main__":
    unittest.main()
