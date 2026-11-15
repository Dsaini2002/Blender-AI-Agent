"""The user wants 10/10: up to 15 rounds, every expected element present, small flaws fixed too,
equal heights for repeated parts and doors standing exactly on the floor."""

from . import _bpy_stub  # noqa: F401

import json
import time
import unittest

from blender_ai_agent.agent import post_verify as pv
from blender_ai_agent.agent import self_correct as sc
from blender_ai_agent.agent.scene_checks import geometry_problems, repeat_key
from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tests.fakes_ext import FakeBridge
from .test_auto_verify import THREE, Case, StubLLM


def strict_critique(score, problems=(), missing=(), severity="low"):
    return json.dumps({"score": score, "summary": "s", "keep": [],
                       "checklist": [{"item": m, "present": False} for m in missing] + [{"item": "ground", "present": True}],
                       "problems": [{"severity": severity, "where": "x", "issue": p, "fix": "f"} for p in problems]})


def box(name, xy, size, z0=0.0, material="m"):
    o = FakeObject(name=name, location=[xy[0], xy[1], z0])
    o.fake_bbox = {"min": [-size[0] / 2, -size[1] / 2, 0.0], "max": [size[0] / 2, size[1] / 2, size[2]]}
    o.material_name = material
    return o


class TestDefaults(unittest.TestCase):

    def test_ten_out_of_ten_fifteen_rounds_strict(self):
        cfg = pv.VerifyConfig()
        self.assertEqual((cfg.pass_score, cfg.max_rounds, cfg.strict_review, cfg.until_fixed), (10.0, 15, True, True))
        self.assertEqual(cfg.stall_rounds, 3)


class TestStrictReview(Case):

    def strict_verifier(self, llm):
        self.cfg.strict_review = True
        self.cfg.pass_score = 10.0
        return self.verifier(llm=llm)

    def facts(self):
        return pv.RunFacts(created=THREE, types={n: "MESH" for n in THREE}, started=time.time())

    def test_reviewer_gets_the_precision_checklist(self):
        llm = StubLLM(strict_critique(10))
        self.strict_verifier(llm).assess("make a house", self.facts())
        system = llm.calls[0]["system"]
        for needed in ("checklist", "flush IN their wall", "EQUAL heights", "Score 10 ONLY"):
            self.assertIn(needed, system)

    def test_small_flaws_and_missing_elements_are_fixed(self):
        report = self.strict_verifier(StubLLM(strict_critique(9, ["door 3 cm above floor"], ["back door"]))).assess(
            "make a house", self.facts())
        self.assertTrue(report.needs_fix)
        self.assertEqual(report.missing, ["back door"])
        text = self.verifier().fix_prompt("make a house", report, 1)
        self.assertIn("MISSING from the scene", text)
        self.assertIn("- back door", text)
        self.assertIn("door 3 cm above floor", text)
        self.assertIn("flawless 10/10", text)

    def test_only_ten_passes(self):
        report = self.strict_verifier(StubLLM(strict_critique(10))).assess("make a house", self.facts())
        self.assertFalse(report.needs_fix)

    def test_non_strict_mode_ignores_low_flaws(self):
        report = self.verifier(llm=StubLLM(strict_critique(8, ["tiny"]))).assess("make a house", self.facts())
        self.assertFalse(report.needs_fix)

    def test_parse_reads_the_checklist(self):
        crit = sc.parse_critique(strict_critique(7, missing=["goal nets", "corner flags"]))
        self.assertEqual(crit.missing, ["goal nets", "corner flags"])

    def test_missing_elements_count_as_progress_to_fix(self):
        a = pv.CheckReport(score=9.0, missing=["x", "y"])
        b = pv.CheckReport(score=9.0, missing=["x"])
        self.assertLess(pv.PostRunVerifier.badness(b), pv.PostRunVerifier.badness(a))


class TestEqualHeights(unittest.TestCase):

    def test_repeat_key(self):
        self.assertEqual(repeat_key("park_lamp2_pole.001"), "park_lamp#_pole")
        self.assertEqual(repeat_key("stadium_light_mast.003"), "stadium_light_mast")
        self.assertEqual(repeat_key("Table_leg_3"), "table_leg_#")

    def test_one_short_leg_is_reported(self):
        legs = [box(f"table_leg_{i}", (i, 0), (0.05, 0.05, 0.75 if i != 3 else 0.6)) for i in range(4)]
        problems = geometry_problems(FakeBridge(objects=legs), [o.name for o in legs])
        uneven = [p for p in problems if "not the same height" in p["issue"]]
        self.assertEqual(len(uneven), 1)
        self.assertEqual(uneven[0]["severity"], "high")
        self.assertIn("table_leg_3 0.60 m", uneven[0]["issue"])
        self.assertIn("0.75 m", uneven[0]["issue"])

    def test_mast_copies_of_different_height_are_reported(self):
        masts = [box("stadium_light_mast", (0, 0), (0.4, 0.4, 20.0)), box("stadium_light_mast.001", (10, 0), (0.4, 0.4, 20.0)),
                 box("stadium_light_mast.002", (20, 0), (0.4, 0.4, 26.0))]
        problems = geometry_problems(FakeBridge(objects=masts), [o.name for o in masts])
        self.assertTrue(any("stadium_light_mast.002 26.00 m" in p["issue"] for p in problems))

    def test_equal_parts_and_natural_variation_are_fine(self):
        objs = [box(f"post_{i}", (i, 0), (0.1, 0.1, 1.0)) for i in range(3)] + \
               [box("pine_tree_1_trunk", (5, 5), (0.3, 0.3, 2.0)), box("pine_tree_2_trunk", (8, 5), (0.3, 0.3, 3.0))]
        problems = geometry_problems(FakeBridge(objects=objs), [o.name for o in objs])
        self.assertFalse([p for p in problems if "not the same height" in p["issue"]])


class TestDoors(unittest.TestCase):

    def test_floating_door_in_front_of_a_wall(self):
        wall = box("house_wall_front", (0, 0), (8, 0.3, 3.0))
        door = box("house_door", (0, -0.2), (1.0, 0.08, 2.1), z0=0.25)
        problems = geometry_problems(FakeBridge(objects=[wall, door]), ["house_wall_front", "house_door"])
        door_p = [p for p in problems if p["where"] == "house_door"]
        self.assertTrue(door_p)
        self.assertIn("0.25 m above the floor", door_p[0]["issue"])

    def test_door_on_an_upper_floor_slab_is_fine(self):
        slab = box("house_floor2", (0, 0), (8, 6, 0.2), z0=3.0)
        door = box("house_door_upstairs", (0, 0), (1.0, 0.08, 2.1), z0=3.2)
        problems = geometry_problems(FakeBridge(objects=[slab, door]), ["house_floor2", "house_door_upstairs"])
        self.assertFalse([p for p in problems if p["where"] == "house_door_upstairs" and "floor" in p["issue"]])

    def test_door_handle_is_not_a_door(self):
        handle = box("house_door_handle", (0, 0), (0.1, 0.05, 0.05), z0=1.0)
        problems = geometry_problems(FakeBridge(objects=[handle]), ["house_door_handle"])
        self.assertFalse([p for p in problems if "a door must stand" in p["issue"]])


if __name__ == "__main__":
    unittest.main()
