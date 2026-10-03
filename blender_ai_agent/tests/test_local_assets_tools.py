from . import _bpy_stub  # noqa: F401

import json
import os
import tempfile
import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.local_assets_tools import (
    PlaceLocalAssetTool, SearchLocalAssetsTool, is_helper_object, models_dir, resolve_entry, search_index,
)
from blender_ai_agent.tools.models import PlaceLocalAssetInput, SearchLocalAssetsInput
from .fakes import FakeBridge, FakeObject

ENTRIES = [
    {"id": "mp-bench", "name": "Bench_01_Art", "project": "pm-momuspark", "project_name": "MomusPark",
     "collection_description": "park props", "attributes": {"Type": "Bench"},
     "tags": ["art", "bench", "nature", "park"],
     "file": "MomusPark/Bench_01_Art.glb", "size": 878104, "license": "CC0"},
    {"id": "tc-torch", "name": "FireTorch01_Art", "project": "pm-tomb-chaser-1", "project_name": "tomb-chaser-1",
     "collection_description": "Egyptian pyramid", "attributes": {}, "tags": ["art", "fire", "torch"],
     "file": "tomb-chaser-1/FireTorch01_Art.glb", "size": 200000, "license": "CC0"},
    {"id": "mp-tree1", "name": "Tree_01_Art", "project": "pm-momuspark", "project_name": "MomusPark",
     "collection_description": "park props", "attributes": {"Type": "Tree"}, "tags": ["art", "tree", "nature"],
     "file": "MomusPark/Tree_01_Art.glb", "size": 300000, "license": "CC0"},
    {"id": "ag-palm", "name": "PalmTree02", "project": "pm-avatar-garden", "project_name": "avatar-garden",
     "collection_description": "garden", "attributes": {}, "tags": ["palm", "tree", "02"],
     "file": "avatar-garden/PalmTree02.glb", "size": 100000, "license": "CC0"},
]


class WithIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("BLENDER_AI_MODELS_DIR")
        os.environ["BLENDER_AI_MODELS_DIR"] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("BLENDER_AI_MODELS_DIR", None)
        else:
            os.environ["BLENDER_AI_MODELS_DIR"] = self.old
        self.tmp.cleanup()

    def write_index(self, entries=ENTRIES, create_files=True):
        with open(os.path.join(self.tmp.name, "index.json"), "w", encoding="utf-8") as handle:
            json.dump({"count": len(entries), "models": entries}, handle)
        if create_files:
            for entry in entries:
                path = os.path.join(self.tmp.name, *entry["file"].split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "wb") as handle:
                    handle.write(b"glTF")


class TestSearch(WithIndex):

    def test_ranking_finds_the_right_model(self):
        self.assertEqual(search_index(ENTRIES, "torch")[0]["id"], "tc-torch")
        self.assertEqual(search_index(ENTRIES, "bench")[0]["id"], "mp-bench")
        self.assertEqual(search_index(ENTRIES, "fire torch")[0]["id"], "tc-torch")
        ids = [e["id"] for e in search_index(ENTRIES, "trees")]           # plural handled
        self.assertEqual(set(ids), {"mp-tree1", "ag-palm"})
        self.assertEqual(search_index(ENTRIES, "palm tree")[0]["id"], "ag-palm")
        self.assertEqual(search_index(ENTRIES, "spaceship"), [])

    def test_project_filter_and_limit(self):
        ids = [e["id"] for e in search_index(ENTRIES, "tree", project="momus")]
        self.assertEqual(ids, ["mp-tree1"])
        self.assertEqual(len(search_index(ENTRIES, "art", limit=1)), 1)

    def test_tool_returns_ids_for_place_local(self):
        self.write_index()
        result = SearchLocalAssetsTool().execute({"query": "tree"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["count"], 2)
        self.assertIn("id", result.data["results"][0])

    def test_helpful_failures(self):
        no_index = SearchLocalAssetsTool().execute({"query": "tree"})
        self.assertFalse(no_index.success)
        self.assertIn("download_models.py", no_index.error)

        self.write_index()
        self.assertIn("No downloaded model matches", SearchLocalAssetsTool().execute({"query": "dragon"}).error)

        with open(os.path.join(self.tmp.name, "index.json"), "w") as handle:
            handle.write("{broken")
        self.assertIn("download_models.py", SearchLocalAssetsTool().execute({"query": "tree"}).error)

    def test_input_validation(self):
        for bad in ({"query": ""}, {"query": "x", "limit": 0}, {"query": "x", "limit": 99}):
            with self.assertRaises(ValueError, msg=str(bad)):
                SearchLocalAssetsInput(**bad)
        self.assertEqual(SearchLocalAssetsInput(query="x", limit="5.0").limit, 5)


class TestPlace(WithIndex):

    def test_places_by_id_and_positions_root_objects(self):
        self.write_index()
        bridge = FakeBridge()
        result = PlaceLocalAssetTool(bridge).execute(
            {"asset_id": "mp-bench", "location": [4, 5, 0], "scale": 2, "yaw_degrees": 90})

        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["license"], "CC0")
        obj = bridge.get_object("Bench_01_Art")
        self.assertEqual([round(v, 6) for v in obj.location], [4.0, 5.0, 0.0])
        self.assertEqual(list(obj.scale), [2, 2, 2])
        self.assertAlmostEqual(obj.rotation_euler[2], 3.141592653589793 / 2)

    def test_places_by_query(self):
        self.write_index()
        bridge = FakeBridge()
        result = PlaceLocalAssetTool(bridge).execute({"query": "torch"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["name"], "FireTorch01_Art")
        self.assertIsNotNone(bridge.get_object("FireTorch01_Art"))

    def test_only_root_objects_are_moved(self):
        self.write_index()

        class HierarchyBridge(FakeBridge):
            def import_model(self, filepath, name=None, scale=None):
                parent = FakeObject(name="Root", location=[1, 0, 0])
                child = FakeObject(name="Child", location=[0, 0, 0.5])
                child.parent = parent
                parent.parent = None
                self._objects.extend([parent, child])
                return [parent, child]

        bridge = HierarchyBridge()
        result = PlaceLocalAssetTool(bridge).execute({"asset_id": "mp-bench", "location": [10, 0, 0]})
        self.assertEqual(result.data["roots"], ["Root"])
        self.assertEqual(bridge.get_object("Root").location, [11.0, 0.0, 0.0])
        self.assertEqual(bridge.get_object("Child").location, [0, 0, 0.5])     # untouched

    def test_collision_proxy_meshes_are_removed_after_import(self):
        """Real bug: Barrel_collider (a white box) showed up with the barrel poking through it."""
        self.write_index()

        class RemovableObject(FakeObject):
            """Asli Blender jaisa: delete hone ke baad `.name` padhne par ReferenceError aata hai."""
            _removed = False

            @property
            def name(self):
                if self._removed:
                    raise ReferenceError("StructRNA of type Object has been removed")
                return self._name

            @name.setter
            def name(self, value):
                self._name = value

        class ColliderBridge(FakeBridge):
            def import_model(self, filepath, name=None, scale=None):
                objs = [RemovableObject(name="Barrel"), RemovableObject(name="Barrel_collider"),
                        RemovableObject(name="Logo")]
                for obj in objs:
                    obj.parent = None
                self._objects.extend(objs)
                return objs

            def delete_object(self, name):
                target = self.get_object(name)
                deleted = super().delete_object(name)
                if target is not None and deleted:
                    target._removed = True
                return deleted

        bridge = ColliderBridge()
        result = PlaceLocalAssetTool(bridge).execute({"asset_id": "mp-bench", "location": [3, 0, 0]})

        self.assertTrue(result.success, result.error)
        names = {o.name for o in bridge._objects}
        self.assertNotIn("Barrel_collider", names)
        self.assertIn("Barrel", names)
        self.assertIn("Logo", names)
        self.assertEqual(result.data["removed_helpers"], ["Barrel_collider"])
        self.assertEqual(result.data["objects"], ["Barrel", "Logo"])
        self.assertEqual(bridge.get_object("Barrel").location, [3.0, 0.0, 0.0])
        self.assertEqual(bridge.get_object("Logo").location, [3.0, 0.0, 0.0])

    def test_readable_refs_work_as_asset_id(self):
        """Real bug: Gemini copied an opaque id wrongly and a creature was placed instead of a fireplace."""
        self.write_index()
        for ref in ("tc-torch", "tomb-chaser-1/FireTorch01_Art", "FireTorch01_Art", "firetorch01_art",
                    "TOMB-CHASER-1/firetorch01_art"):
            bridge = FakeBridge()
            result = PlaceLocalAssetTool(bridge).execute({"asset_id": ref})
            self.assertTrue(result.success, f"{ref}: {result.error}")
            self.assertEqual(result.data["name"], "FireTorch01_Art", ref)

    def test_ambiguous_name_asks_for_collection_ref(self):
        twin = dict(ENTRIES[0], id="x-bench", project="pm-other", project_name="other",
                    file="other/Bench_01_Art.glb")
        self.write_index(ENTRIES + [twin])
        result = PlaceLocalAssetTool(FakeBridge()).execute({"asset_id": "Bench_01_Art"})
        self.assertFalse(result.success)
        self.assertIn("MomusPark/Bench_01_Art", result.error)
        self.assertIn("other/Bench_01_Art", result.error)
        ok = PlaceLocalAssetTool(FakeBridge()).execute({"asset_id": "other/Bench_01_Art"})
        self.assertTrue(ok.success, ok.error)

    def test_wrong_id_with_a_query_is_caught(self):
        self.write_index()
        tool = PlaceLocalAssetTool(FakeBridge())
        wrong = tool.execute({"asset_id": "mp-bench", "query": "torch"})   # id says bench, query says torch
        self.assertFalse(wrong.success)
        self.assertIn("does not match", wrong.error)
        self.assertIn("FireTorch01_Art", wrong.error)                       # tells Gemini the right one
        self.assertTrue(tool.execute({"asset_id": "tc-torch", "query": "torch"}).success)

    def test_unknown_id_suggests_similar_models(self):
        self.write_index()
        result = PlaceLocalAssetTool(FakeBridge()).execute({"asset_id": "torch"})   # not an id, not an exact name
        self.assertFalse(result.success)
        self.assertIn("No downloaded model with id", result.error)
        self.assertIn("Did you mean", result.error)
        self.assertIn("tomb-chaser-1/FireTorch01_Art", result.error)

    def test_search_results_carry_a_readable_ref(self):
        self.write_index()
        result = SearchLocalAssetsTool().execute({"query": "torch"})
        self.assertEqual(result.data["results"][0]["ref"], "tomb-chaser-1/FireTorch01_Art")

    def test_resolve_entry_directly(self):
        entry, candidates = resolve_entry(ENTRIES, "ag-palm")
        self.assertEqual(entry["name"], "PalmTree02")
        self.assertEqual(resolve_entry(ENTRIES, ""), (None, []))
        self.assertEqual(resolve_entry(ENTRIES, "nothing-here"), (None, []))

    def test_helper_name_detection(self):
        for name in ("Barrel_collider", "Wall_Collision", "UCX_Wall_01", "ubx_box", "Door_col", "HitBox"):
            self.assertTrue(is_helper_object(name), name)
        for name in ("Barrel", "Bench_01", "Logo", "Collar", "Column_Regular", "Colosseum", "Coin_Art", ""):
            self.assertFalse(is_helper_object(name), name)

    def test_failures(self):
        self.assertIn("download_models.py", PlaceLocalAssetTool(FakeBridge()).execute({"query": "tree"}).error)
        self.write_index()
        tool = PlaceLocalAssetTool(FakeBridge())
        self.assertIn("No downloaded model with id", tool.execute({"asset_id": "nope"}).error)
        self.assertIn("No downloaded model matches", tool.execute({"query": "dragon"}).error)
        os.remove(os.path.join(self.tmp.name, "MomusPark", "Bench_01_Art.glb"))
        self.assertIn("missing on disk", tool.execute({"asset_id": "mp-bench"}).error)

    def test_input_needs_id_or_query(self):
        with self.assertRaises(ValueError):
            PlaceLocalAssetInput()
        data = PlaceLocalAssetInput(query="tree", location="[1,2,3]", scale="2")
        self.assertEqual(data.location, [1.0, 2.0, 3.0])
        self.assertEqual(data.scale, 2.0)

    def test_metadata_and_default_dir(self):
        self.assertEqual(SearchLocalAssetsTool().permission, Permission.READ_ONLY)
        self.assertEqual(PlaceLocalAssetTool(FakeBridge()).permission, Permission.SAFE_WRITE)
        os.environ.pop("BLENDER_AI_MODELS_DIR")
        try:
            self.assertTrue(models_dir().endswith(os.path.join("BlenderAIAgent", "models")))
        finally:
            os.environ["BLENDER_AI_MODELS_DIR"] = self.tmp.name


if __name__ == "__main__":
    unittest.main()