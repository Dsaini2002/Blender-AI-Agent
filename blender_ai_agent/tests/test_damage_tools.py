from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.mesh_tools import DamageMeshTool
from blender_ai_agent.tools.models import DamageMeshInput
from .fakes import FakeObject
from .fakes_ext import FakeBridge


class TestDamageMeshInput(unittest.TestCase):

    def test_defaults(self):
        data = DamageMeshInput(object_name="Bottle")
        self.assertEqual((data.region, data.style, data.portion, data.strength, data.detail), ("top", "broken", 0.25, 0.15, 1))

    def test_everyday_words_are_understood(self):
        for given, expected in (("neck", "top"), ("Lid", "top"), ("rim", "top"), ("upper", "top"), ("base", "bottom"),
                                ("lower", "bottom"), ("right side", "right"), ("whole", "all"), ("TOP", "top")):
            self.assertEqual(DamageMeshInput(object_name="B", region=given).region, expected, given)
        for given, expected in (("cracked", "broken"), ("shattered", "broken"), ("damaged", "broken"),
                                ("chip", "chipped"), ("dent", "dented"), ("crushed", "dented"), ("worn", "rough"),
                                ("scratched", "rough"), ("old", "rough"), ("Broken", "broken")):
            self.assertEqual(DamageMeshInput(object_name="B", style=given).style, expected, given)

    def test_numbers_accept_llm_style_values(self):
        data = DamageMeshInput(object_name="B", portion="0.3", strength="0.2", seed="7.0", detail="2")
        self.assertEqual((data.portion, data.strength, data.seed, data.detail), (0.3, 0.2, 7, 2))

    def test_invalid_values_are_rejected_with_helpful_messages(self):
        for kwargs in ({"object_name": ""}, {"region": "sideways"}, {"style": "melted"}, {"portion": 0.0},
                       {"portion": 2}, {"strength": 0}, {"strength": 0.9}, {"detail": 3}, {"seed": "x"}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                DamageMeshInput(**{"object_name": "B", **kwargs})
        with self.assertRaises(ValueError) as ctx:
            DamageMeshInput(object_name="B", region="sideways")
        self.assertIn("top", str(ctx.exception))


class TestDamageMeshTool(unittest.TestCase):

    def test_the_bottle_example(self):
        bridge = FakeBridge(objects=[FakeObject(name="Bottle")])
        result = DamageMeshTool(bridge).execute(
            {"object_name": "Bottle", "region": "neck", "style": "cracked", "strength": "0.12"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(bridge.get_object("Bottle").damage["region"], "top")
        self.assertEqual(bridge.get_object("Bottle").damage["style"], "broken")
        self.assertEqual(bridge.get_object("Bottle").damage["strength"], 0.12)
        self.assertEqual(result.data["style"], "broken")
        self.assertIn("removed_faces", result.data)

    def test_aliases_from_the_base_class_still_work(self):
        bridge = FakeBridge(objects=[FakeObject(name="Vase")])
        result = DamageMeshTool(bridge).execute({"name": "Vase"})          # 'name' is not a field -> dropped -> missing
        self.assertFalse(result.success)
        ok = DamageMeshTool(bridge).execute({"object_name": "Vase"})
        self.assertTrue(ok.success, ok.error)

    def test_missing_object_is_a_clean_failure(self):
        result = DamageMeshTool(FakeBridge()).execute({"object_name": "Ghost"})
        self.assertFalse(result.success)
        self.assertIn("not found", result.error)

    def test_non_mesh_object_is_a_clean_failure(self):
        bridge = FakeBridge(objects=[FakeObject(name="Lamp", type_="LIGHT")])
        self.assertFalse(DamageMeshTool(bridge).execute({"object_name": "Lamp"}).success)

    def test_invalid_input_is_a_clean_failure(self):
        bridge = FakeBridge(objects=[FakeObject(name="Bottle")])
        result = DamageMeshTool(bridge).execute({"object_name": "Bottle", "style": "melted"})
        self.assertFalse(result.success)
        self.assertIn("style", result.error)

    def test_metadata_tells_the_model_how_to_use_it(self):
        tool = DamageMeshTool(FakeBridge())
        self.assertEqual(tool.name, "mesh.damage")
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)
        for word in ("broken", "bottle", "top", "region", "strength", "imported"):
            self.assertIn(word, tool.description)


if __name__ == "__main__":
    unittest.main()