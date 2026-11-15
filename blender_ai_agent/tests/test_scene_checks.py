from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.post_verify import CheckReport, PostRunVerifier
from blender_ai_agent.agent.scene_checks import geometry_problems
from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tests.fakes_ext import FakeBridge


def obj(name, z, bbox=((-0.5, -0.5, 0.0), (0.5, 0.5, 1.0)), xy=(0.0, 0.0), material="Mat"):
    o = FakeObject(name=name, location=[xy[0], xy[1], z])
    o.fake_bbox = {"min": list(bbox[0]), "max": list(bbox[1])}
    o.material_name = material
    return o


class TestGeometryProblems(unittest.TestCase):

    def test_floating_object_is_found_with_a_fix(self):
        bridge = FakeBridge(objects=[obj("Cliff", 3.0), obj("Tree", 0.0, xy=(5, 5))])
        problems = geometry_problems(bridge, ["Cliff", "Tree"])
        self.assertEqual([p["where"] for p in problems], ["Cliff"])
        self.assertEqual(problems[0]["severity"], "high")
        self.assertIn("snap_to_ground", problems[0]["fix"])

    def test_object_resting_on_another_is_fine(self):
        table = obj("Table", 0.0, bbox=((-1, -1, 0), (1, 1, 0.8)))
        book = obj("Book", 0.8, bbox=((-0.1, -0.1, 0), (0.1, 0.1, 0.05)))
        self.assertEqual(geometry_problems(FakeBridge(objects=[table, book]), ["Table", "Book"]), [])

    def test_things_meant_to_float_are_ignored(self):
        bridge = FakeBridge(objects=[obj("Cloud_01", 8.0), obj("campfire_flame", 0.4)])
        self.assertEqual(geometry_problems(bridge, ["Cloud_01", "campfire_flame"]), [])

    def test_sunk_object_and_missing_material(self):
        bridge = FakeBridge(objects=[obj("Rock", -3.0), obj("Box", 0.0, material=None)])
        problems = {p["where"]: p for p in geometry_problems(bridge, ["Rock", "Box"])}
        self.assertIn("below the ground", problems["Rock"]["issue"])
        self.assertEqual(problems["Box"]["severity"], "medium")


class TestFixPromptCarriesGeometry(unittest.TestCase):

    def test_geometry_problems_are_in_the_fix_prompt(self):
        report = CheckReport(created=["Cliff"], geometry=[{"severity": "high", "where": "Cliff",
                                                           "issue": "floats 3.00 m above the ground", "fix": "object.snap_to_ground"}])
        verifier = PostRunVerifier.__new__(PostRunVerifier)
        text = PostRunVerifier.fix_prompt(verifier, "make a waterfall", report, 1)
        self.assertIn("Geometry problems", text)
        self.assertIn("Cliff: floats 3.00 m", text)


if __name__ == "__main__":
    unittest.main()
