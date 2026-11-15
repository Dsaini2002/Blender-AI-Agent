from . import _bpy_stub  # noqa: F401

import json
import os
import tempfile
import unittest

from blender_ai_agent.agent.scene_checks import geometry_problems
from blender_ai_agent.tests.fakes import FakeObject
from blender_ai_agent.tests.fakes_ext import FakeBridge
from blender_ai_agent.tools.local_assets_tools import PlaceLocalAssetTool, typical_height


class ScaledBridge(FakeBridge):
    """measure_objects that respects scale, like real Blender."""

    def __init__(self, raw_box, **kwargs):
        super().__init__(**kwargs)
        self.raw_box = raw_box

    def measure_objects(self, names):
        obj = self.get_object(names[0])
        if obj is None:
            return None
        lo = [self.raw_box[0][k] * obj.scale[k] + obj.location[k] for k in range(3)]
        hi = [self.raw_box[1][k] * obj.scale[k] + obj.location[k] for k in range(3)]
        return {"min": lo, "max": hi}

    def bake_scale(self, name):
        obj = self.get_object(name)
        s = list(obj.scale)
        if all(abs(v - 1.0) < 1e-6 for v in s):
            return False
        self.raw_box = ([self.raw_box[0][k] * s[k] for k in range(3)], [self.raw_box[1][k] * s[k] for k in range(3)])
        obj.scale = [1.0, 1.0, 1.0]
        return True


class TestRealSize(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("BLENDER_AI_MODELS_DIR")
        os.environ["BLENDER_AI_MODELS_DIR"] = self.tmp.name
        entry = {"id": "b1", "name": "Park_Bench", "project": "p", "project_name": "park", "collection_description": "",
                 "attributes": {}, "tags": ["park", "bench"], "file": "park/Park_Bench.glb", "size": 1, "license": "CC0"}
        with open(os.path.join(self.tmp.name, "index.json"), "w", encoding="utf-8") as handle:
            json.dump({"models": [entry]}, handle)
        os.makedirs(os.path.join(self.tmp.name, "park"), exist_ok=True)
        with open(os.path.join(self.tmp.name, "park", "Park_Bench.glb"), "wb") as handle:
            handle.write(b"glTF")

    def tearDown(self):
        if self.old is None:
            os.environ.pop("BLENDER_AI_MODELS_DIR", None)
        else:
            os.environ["BLENDER_AI_MODELS_DIR"] = self.old
        self.tmp.cleanup()

    def test_typical_heights(self):
        self.assertEqual(typical_height("street lamp"), 4.5)
        self.assertEqual(typical_height("Park_Bench"), 0.85)
        self.assertIsNone(typical_height("spaceship"))

    def test_tiny_import_is_scaled_to_real_size_and_stands_on_the_ground(self):
        bridge = ScaledBridge(([-0.5, -0.2, -0.05], [0.5, 0.2, 0.05]))        # 10 cm tall bench (wrong units)
        result = PlaceLocalAssetTool(bridge).execute({"query": "bench", "location": [2, 0, 0]})
        self.assertTrue(result.success, result.error)
        self.assertAlmostEqual(result.data["size"][2], 0.85, places=2)
        self.assertAlmostEqual(result.data["auto_scale"], 8.5, places=2)
        box = bridge.measure_objects([result.data["roots"][0]])
        self.assertAlmostEqual(box["min"][2], 0.0, places=3)
        self.assertAlmostEqual(box["max"][2] - box["min"][2], 0.85, places=2)
        # The import scale is baked in, so the root reads 1.0 and cannot be "fixed" 100x bigger later.
        self.assertTrue(result.data["scale_baked"])
        self.assertEqual(list(bridge.get_object(result.data["roots"][0]).scale), [1.0, 1.0, 1.0])

    def test_explicit_scale_is_respected(self):
        bridge = ScaledBridge(([-0.5, -0.2, 0.0], [0.5, 0.2, 0.1]))
        result = PlaceLocalAssetTool(bridge).execute({"query": "bench", "scale": 2.0})
        self.assertIsNone(result.data["auto_scale"])

    def test_reasonable_size_is_left_alone(self):
        bridge = ScaledBridge(([-0.8, -0.3, 0.0], [0.8, 0.3, 0.9]))
        self.assertIsNone(PlaceLocalAssetTool(bridge).execute({"query": "bench"}).data["auto_scale"])


class TestBareGround(unittest.TestCase):

    def test_big_white_ground_is_a_high_problem(self):
        ground = FakeObject(name="park_ground")
        ground.fake_bbox = {"min": [-10, -10, 0], "max": [10, 10, 0.01]}
        ground.material_name = None
        problems = geometry_problems(FakeBridge(objects=[ground]), ["park_ground"])
        self.assertEqual(problems[0]["severity"], "high")
        self.assertIn("assign_to=['park_ground']", problems[0]["fix"])


if __name__ == "__main__":
    unittest.main()
