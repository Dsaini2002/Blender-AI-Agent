from . import _bpy_stub  # noqa: F401

import json
import os
import tempfile
import unittest

from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.skills.builtins.library_props import LibraryPropSkill
from blender_ai_agent.skills.registry import SkillRegistry
from blender_ai_agent.tools.local_assets_tools import PlaceLocalAssetTool, SearchLocalAssetsTool, load_index
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes_ext import FakeBridge


def entry(i, name, project, tags):
    return {"id": i, "name": name, "project": "pm-" + project, "project_name": project, "collection_description": "",
            "attributes": {}, "tags": tags, "file": f"{project}/{name}.glb", "size": 10, "license": "CC0"}


ENTRIES = [
    entry("mf-bottle", "Bottle_Wine", "medieval-fair", ["bottle", "wine"]),
    entry("mf-bottleneck", "Bottleneck_Prop", "medieval-fair", ["bottleneck", "prop"]),
    entry("mp-bench", "Bench_01_Art", "MomusPark", ["bench", "art"]),
    entry("mp-cube", "Cube_Seat", "MomusPark", ["cube", "seat"]),
    entry("tc-torch", "Torch_Art", "tomb-chaser-1", ["torch", "art"]),
]


class TestAutomaticDownloadedFallback(unittest.TestCase):
    """'Add a bottle' -> the agent cannot build it itself -> take it from the downloaded models."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("BLENDER_AI_MODELS_DIR")
        os.environ["BLENDER_AI_MODELS_DIR"] = self.tmp.name
        self.write_index()

    def tearDown(self):
        if self.old is None:
            os.environ.pop("BLENDER_AI_MODELS_DIR", None)
        else:
            os.environ["BLENDER_AI_MODELS_DIR"] = self.old
        self.tmp.cleanup()

    def write_index(self, entries=ENTRIES):
        with open(os.path.join(self.tmp.name, "index.json"), "w", encoding="utf-8") as handle:
            json.dump({"models": entries}, handle)
        for item in entries:
            path = os.path.join(self.tmp.name, *item["file"].split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as handle:
                handle.write(b"glTF")

    def skill(self):
        bridge = FakeBridge()
        registry = ToolRegistry()
        for tool in (PlaceLocalAssetTool(bridge), SearchLocalAssetsTool(bridge), SceneInspectTool(SceneInspector(bridge))):
            registry.register(tool)
        return LibraryPropSkill(ToolCaller(registry)), bridge

    def test_simple_unknown_objects_found_in_the_downloads_are_picked_up(self):
        skill, _ = self.skill()
        for text, phrase in (("add a bottle", "bottle"), ("make a bench", "bench"), ("place the torch", None),
                             ("create a bottle please", "bottle"), ("bottle banao", "bottle")):
            if phrase is None:
                continue                                    # 'torch' is a built-in -> handled by the 0.9 path
            self.assertEqual(skill._match_fallback(text), phrase, text)
            self.assertEqual(skill.can_handle(text), 0.85, text)

    def test_places_the_real_model_without_the_llm(self):
        skill, bridge = self.skill()
        result = skill.execute({"task": "add a bottle"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["name"], "Bottle_Wine")
        self.assertEqual(result.data["source"], "downloaded")
        self.assertIsNotNone(bridge.get_object("Bottle_Wine"))

    def test_things_the_agent_can_build_itself_are_left_alone(self):
        skill, _ = self.skill()
        for text in ("add a cube", "make a red cube", "create a sphere", "add a floor", "make a room", "add a wall",
                     "add a light", "create a monkey"):
            self.assertEqual(skill._match_fallback(text), None, text)
            self.assertEqual(skill.can_handle(text), 0.0, text)

    def test_requests_with_colour_count_or_place_go_to_the_llm(self):
        skill, _ = self.skill()
        for text in ("add a red bottle", "add 3 bottles", "add a bottle next to the bench", "add a bottle and a bench",
                     "add a bottle named Drink", "move the bottle"):
            self.assertIsNone(skill._match_fallback(text), text)

    def test_only_whole_word_matches_count(self):
        skill, _ = self.skill()
        self.assertEqual(skill._match_fallback("add a bottle"), "bottle")            # Bottle_Wine, whole word
        self.assertIsNone(skill._match_fallback("add a bot"))                       # partial words are not enough
        self.assertIsNone(skill._match_fallback("add a dragon"))                    # nothing like it downloaded
        self.assertIsNone(skill._match_fallback("add a neck"))

    def test_built_in_library_still_wins_and_explicit_hint_still_wins_over_both(self):
        skill, _ = self.skill()
        self.assertEqual(skill.can_handle("add a torch"), 0.9)                       # built-in
        self.assertEqual(skill.can_handle("add a torch from the downloaded models"), 0.95)
        self.assertIsNone(skill._match_fallback("add a bottle from the downloaded models"))   # handled by _match_local

    def test_without_an_index_nothing_is_hijacked(self):
        os.remove(os.path.join(self.tmp.name, "index.json"))
        skill, _ = self.skill()
        self.assertIsNone(skill._match_fallback("add a bottle"))
        self.assertEqual(skill.can_handle("add a bottle"), 0.0)

    def test_registry_prefers_built_in_over_fallback(self):
        skill, _ = self.skill()
        registry = SkillRegistry()
        registry.register(skill)
        self.assertEqual(registry.find_best_match("add a bottle").name, "library_props")
        self.assertIsNone(registry.find_best_match("add a dragon"))

    def test_index_is_cached_until_the_file_changes(self):
        first = load_index()
        self.assertIs(load_index(), first)                                           # same object -> cached
        self.write_index(ENTRIES[:2])
        os.utime(os.path.join(self.tmp.name, "index.json"), (1, 1))                  # force a new mtime
        self.assertEqual(len(load_index()), 2)


if __name__ == "__main__":
    unittest.main()