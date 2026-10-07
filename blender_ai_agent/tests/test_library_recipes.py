from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools import shader_nodes as sn
from blender_ai_agent.tools.library_tools import LibraryPlaceTool, load_library, place_model
from .fakes_ext import FakeBridge


def _ensure_lights(bridge_class):
    if not hasattr(bridge_class, "create_light"):
        def create_light(self, name, *args, **kwargs):
            from .fakes import FakeObject as _Obj
            obj = _Obj(name=name, type_="LIGHT")
            self._objects.append(obj)
            return obj
        bridge_class.create_light = create_light
    return bridge_class


_ensure_lights(FakeBridge)


class NodeBridge(FakeBridge):
    def __init__(self, fail_on=None):
        super().__init__()
        self.node_calls, self.fail_on = [], fail_on or ()

    def build_node_material(self, name, spec, replace=True):
        if any(f in name for f in self.fail_on):
            raise ValueError("this Blender cannot build that")
        self.node_calls.append((name, spec))
        return {"name": name, "nodes": len(spec.nodes), "links": len(spec.links), "notes": []}


class TestPrefabsUseRecipes(unittest.TestCase):

    def test_every_recipe_named_in_the_library_is_valid(self):
        count = 0
        for model, spec in load_library().items():
            for key, material in spec["materials"].items():
                if "recipe" in material:
                    count += 1
                    built = sn.build_recipe(material["recipe"], material.get("params"))
                    self.assertTrue(built.nodes, f"{model}.{key}")
                    self.assertIn("color", material, f"{model}.{key}: saada rang fallback ke liye chahiye")
        self.assertGreaterEqual(count, 20)

    def test_the_campfire_now_has_real_fire_stone_wood_and_embers(self):
        materials = load_library()["campfire"]["materials"]
        self.assertEqual({k: v.get("recipe") for k, v in materials.items()},
                         {"stone": "rough_stone", "wood": "charred_wood", "ember": "ember", "flame_outer": "fire_flame", "flame_mid": "fire_flame",
                          "flame_inner": "fire_flame"})
        colours = {k: tuple(materials[k]["params"]["color"]) for k in ("flame_outer", "flame_mid", "flame_inner")}
        self.assertEqual(len(set(colours.values())), 3)                                   # teen alag rang ki parten

    def test_lamps_glow_and_trees_have_bark(self):
        library = load_library()
        self.assertEqual(library["lantern"]["materials"]["glass"]["recipe"], "glow")
        self.assertEqual(library["street_lamp"]["materials"]["bulb"]["recipe"], "glow")
        self.assertEqual(library["pine_tree"]["materials"]["trunk"]["recipe"], "wood_grain")
        self.assertNotIn("recipe", library["pine_tree"]["materials"]["leaves"])               # patte abhi saade rang


class TestPlacing(unittest.TestCase):

    def place(self, bridge, model="campfire", colors=None):
        return place_model(bridge, model, load_library()[model], [0, 0, 0], 1.0, 0.0, "", colors)

    def test_recipe_materials_are_built_and_the_parts_use_them(self):
        bridge = NodeBridge()
        created = self.place(bridge)
        names = sorted(n for n, _ in bridge.node_calls)
        self.assertEqual(names, ["campfire_ember_mat", "campfire_flame_inner_mat", "campfire_flame_mid_mat", "campfire_flame_outer_mat",
                                 "campfire_stone_mat", "campfire_wood_mat"])
        self.assertTrue(created["meshes"] and created["curves"])
        self.assertEqual(len(created["lights"]), 1)                                       # aag ki asli light bhi
        specs = dict(bridge.node_calls)
        flame = specs["campfire_flame_inner_mat"]
        self.assertEqual(next(n for n in flame.nodes if n.id == "em").inputs["Color"], [1.0, 0.62, 0.1, 1.0])

    def test_without_node_support_or_when_blender_refuses_it_falls_back_to_plain_colours(self):
        plain = FakeBridge()                                                             # build_node_material hai hi nahi
        created = self.place(plain)
        self.assertTrue(created["meshes"])
        self.assertTrue(plain.get_material("campfire_stone_mat"))
        refusing = NodeBridge(fail_on=("flame",))
        created = self.place(refusing)
        self.assertEqual(sorted(n for n, _ in refusing.node_calls), ["campfire_ember_mat", "campfire_stone_mat", "campfire_wood_mat"])
        self.assertTrue(refusing.get_material("campfire_flame_mid_mat"))
        self.assertTrue(refusing.get_material("campfire_flame_outer_mat"))                  # sirf wahi saade rang par
        self.assertTrue(created["curves"])

    def test_user_colour_overrides_reach_the_recipe(self):
        bridge = NodeBridge()
        self.place(bridge, "campfire", {"flame_outer": [0.1, 0.3, 1.0]})
        flame = dict(bridge.node_calls)["campfire_flame_outer_mat"]
        self.assertEqual(next(n for n in flame.nodes if n.id == "em").inputs["Color"], [0.1, 0.3, 1.0, 1.0])
        bridge = NodeBridge()
        self.place(bridge, "log_seat", {"wood": [0.2, 0.4, 0.8]})
        wood = dict(bridge.node_calls)["log_seat_wood_mat"]
        ramp = next(n for n in wood.nodes if n.type == "ValToRGB").ramp
        self.assertEqual(ramp[1][1], [0.2, 0.4, 0.8, 1.0])                                  # light
        self.assertAlmostEqual(ramp[0][1][0], 0.08)                                       # dark = 0.4 x

    def test_the_tool_still_places_every_prefab(self):
        for model in load_library():
            bridge = NodeBridge()
            result = LibraryPlaceTool(bridge).execute({"model": model})
            self.assertTrue(result.success, f"{model}: {result.error}")


class TestViewportTint(unittest.TestCase):

    def test_flames_and_glow_get_their_colour_in_the_solid_viewport(self):
        self.assertEqual(sn.viewport_color(sn.build_recipe("fire_flame", {"color": [1.0, 0.2, 0.0, 1.0]})), [1.0, 0.2, 0.0, 1.0])
        self.assertEqual(sn.viewport_color(sn.build_recipe("glow", {"color": [0.2, 0.4, 1.0]})), [0.2, 0.4, 1.0, 1.0])
        self.assertEqual(sn.viewport_color(sn.build_recipe("car_paint", {"color": [0, 0, 1, 1]})), [0, 0, 1, 1])
        self.assertIsNone(sn.viewport_color(sn.build_recipe("smoke_volume")))                # volume ka koi surface rang nahi


if __name__ == "__main__":
    unittest.main()