from . import _bpy_stub  # noqa: F401

import math
import unittest
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent.bridge import blender_bridge
from blender_ai_agent.bridge.blender_bridge import BlenderBridge
from blender_ai_agent.tools import shader_nodes as sn
from blender_ai_agent.tools.shader_tools import (MaterialNodesTool, MaterialRecipeInput, MaterialRecipeTool, PRESETS, RenderSetupInput,
                                                 RenderSetupTool)
from .fakes import FakeObject
from .fakes_ext import FakeBridge


# ----------------------------------------------------------------------------- a fake Blender node tree built from our own socket table
class FakeSocket:
    def __init__(self, name, is_input, default=0.0):
        self.name, self.is_input, self.default_value, self.unavailable = name, is_input, default, False


class FakeElement:
    def __init__(self, position=0.0):
        self.position, self.color = position, [0, 0, 0, 1]


class FakeRamp:
    def __init__(self):
        self.elements = FakeElements([FakeElement(0.0), FakeElement(1.0)])


class FakeElements(list):
    def new(self, position):
        element = FakeElement(position)
        self.append(element)
        return element

    def remove(self, element):
        super().remove(element)


class FakeNode:
    def __init__(self, idname):
        short = next(k for k, v in sn.NODE_TYPES.items() if v == idname)
        inputs, outputs = sn.SOCKETS.get(short, ([], []))
        self.idname, self.short, self.name, self.label, self.location = idname, short, "", "", (0, 0)
        self.inputs = [FakeSocket(n, True, [0.8, 0.8, 0.8, 1.0] if n in ("Color", "Base Color", "Emission Color", "Color1", "Color2") else
                                  [0.0, 0.0, 0.0] if n in ("Vector", "Location", "Rotation", "Scale") and short == "Mapping" else 0.0) for n in inputs]
        self.outputs = [FakeSocket(n, False) for n in outputs]
        if short == "ValToRGB":
            self.color_ramp = FakeRamp()
        self.image = None


class FakeNodes(list):
    def new(self, idname):
        if idname == "ShaderNodeDoesNotExist":
            raise RuntimeError("unknown node type")
        node = FakeNode(idname)
        self.append(node)
        return node

    def clear(self):
        del self[:]


class FakeLinks(list):
    def new(self, out_socket, in_socket):
        assert not out_socket.is_input and in_socket.is_input, "link direction must be output -> input"
        self.append((out_socket, in_socket))


class FakeMaterial:
    def __init__(self, name):
        self.name = name
        self.node_tree = SimpleNamespace(nodes=FakeNodes(), links=FakeLinks())
        self.surface_render_method = "DITHERED"
        self.use_backface_culling = True


class FakeMaterials:
    def __init__(self):
        self.items = {}

    def get(self, name):
        return self.items.get(name)

    def new(self, name):
        self.items[name] = FakeMaterial(name)
        return self.items[name]


def fake_bpy():
    return SimpleNamespace(data=SimpleNamespace(materials=FakeMaterials(), objects=SimpleNamespace(get=lambda n: None),
                                                images=SimpleNamespace(load=lambda path, check_existing=True: SimpleNamespace(
                                                    filepath=path, colorspace_settings=SimpleNamespace(name="sRGB")))))


class BridgeCase(unittest.TestCase):
    def setUp(self):
        self.bpy = fake_bpy()
        patcher = mock.patch.object(blender_bridge, "bpy", self.bpy)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.bridge = BlenderBridge.__new__(BlenderBridge)

    def build(self, name, nodes, links, settings=None, replace=True):
        spec = sn.parse_material_spec(nodes, links, settings)
        return self.bridge.build_node_material(name, spec, replace), self.bpy.data.materials.get(name)


# ----------------------------------------------------------------------------- spec validation
class TestSpec(unittest.TestCase):
    OUT = {"id": "out", "type": "OutputMaterial"}

    def parse(self, nodes, links=(), settings=None):
        return sn.parse_material_spec(nodes, list(links), settings)

    def test_minimal_and_full_idnames(self):
        spec = self.parse([self.OUT, {"id": "em", "type": "ShaderNodeEmission", "inputs": {"Strength": 5}}], [["em.Emission", "out.Surface"]])
        self.assertEqual([n.type for n in spec.nodes], ["OutputMaterial", "Emission"])
        self.assertEqual(spec.links, [("em", "Emission", "out", "Surface")])
        self.assertEqual(spec.nodes[1].inputs["Strength"], 5)

    def test_every_kind_of_mistake_has_a_helpful_message(self):
        em = {"id": "em", "type": "Emission"}
        cases = [
            ([], "non-empty"), ("nodes", "non-empty"), ([self.OUT, self.OUT | {"id": "o2"}], "exactly one OutputMaterial"), ([em], "exactly one OutputMaterial"),
            ([self.OUT, {"id": "a", "type": "Banana"}], "unknown node type"), ([self.OUT, {"id": "1bad", "type": "Emission"}], "'id' must be"),
            ([self.OUT, em, em], "duplicate id"), ([self.OUT, {"id": "x", "type": "Emission", "props": {"location": 3}}], "not allowed"),
            ([self.OUT, {"id": "x", "type": "Emission", "inputs": {"Nope": 1}}], "no input 'Nope'"),
            ([self.OUT, {"id": "x", "type": "Emission", "inputs": {"Color": [1, 2, 3, 4, 5]}}], "1-4 numbers"),
            ([self.OUT, {"id": "x", "type": "Emission", "ramp": [[0, [0, 0, 0]], [1, [1, 1, 1]]]}], "only belongs on a ValToRGB"),
            ([self.OUT, {"id": "x", "type": "ValToRGB", "ramp": [[0, [0, 0, 0]]]}], "2-16 stops"),
            ([self.OUT, {"id": "x", "type": "Emission", "image": "a.png"}], "only belongs on a TexImage"),
            ([self.OUT, {"id": "x", "type": "TexImage", "image": "a.png", "colorspace": "weird"}], "colorspace"),
            ([self.OUT, {"id": "x", "type": "Emission", "location": [1]}], "location must be"),
        ]
        for nodes, fragment in cases:
            with self.assertRaises(ValueError, msg=str(nodes)) as ctx:
                self.parse(nodes)
            self.assertIn(fragment, str(ctx.exception), str(nodes))

    def test_link_mistakes_name_the_valid_sockets(self):
        nodes = [self.OUT, {"id": "n", "type": "TexNoise"}, {"id": "e", "type": "Emission"}]
        for link, fragment in ((["n.Facc", "e.Color"], "Outputs: Fac, Color"), (["n.Fac", "e.Colour"], "Inputs: Color, Strength"), (["zz.Fac", "e.Color"], "unknown node id"),
                               (["n", "e.Color"], "node_id.Socket"), (["n.Fac"], "must be")):
            with self.assertRaises(ValueError, msg=str(link)) as ctx:
                self.parse(nodes, [link])
            self.assertIn(fragment, str(ctx.exception), str(link))
        self.parse(nodes, [["n.0", "e.1"], ["n.Fac", "e.Color"]])                  # numbers hamesha chalte hain

    def test_settings_and_limits(self):
        nodes = [self.OUT]
        self.assertEqual(self.parse(nodes, settings={"surface_render_method": "BLENDED", "use_backface_culling": False}).settings,
                         {"surface_render_method": "BLENDED", "use_backface_culling": False})
        for settings in ({"surface_render_method": "WRONG"}, {"unknown": 1}):
            with self.assertRaises(ValueError):
                self.parse(nodes, settings=settings)
        with self.assertRaises(ValueError):
            self.parse([self.OUT] + [{"id": f"n{i}", "type": "Value"} for i in range(sn.MAX_NODES)])
        with self.assertRaises(ValueError):
            self.parse([self.OUT, {"id": "v", "type": "Value"}], [["v.Value", "out.Surface"]] * (sn.MAX_LINKS + 1))

    def test_ramp_is_sorted_and_clamped(self):
        spec = self.parse([self.OUT, {"id": "r", "type": "ValToRGB", "ramp": [[0.9, [1, 1, 1]], [-1, [0, 0, 0, 1]]]}])
        self.assertEqual([stop[0] for stop in spec.nodes[1].ramp], [0.0, 0.9])
        self.assertEqual(spec.nodes[1].ramp[1][1], [1.0, 1.0, 1.0, 1.0])               # rgb -> rgba

    def test_layout_puts_the_output_on_the_right_and_upstream_on_the_left(self):
        spec = sn.build_recipe("fire_flame")
        place = sn.layout(spec)
        self.assertEqual(place["out"][0], 0.0)
        self.assertLess(place["tc"][0], place["noise"][0])
        self.assertLess(place["noise"][0], place["mix"][0])
        self.assertEqual(len(set(place.values())), len(spec.nodes))                    # koi do node ek jagah nahi


class TestRecipes(unittest.TestCase):

    def test_every_recipe_is_valid_with_defaults_and_has_one_output(self):
        for name in sn.RECIPES:
            spec = sn.build_recipe(name)
            self.assertEqual(sum(1 for n in spec.nodes if n.type == "OutputMaterial"), 1, name)
            self.assertTrue(spec.links, name)
        self.assertEqual(len(sn.RECIPES), 14)

    def test_params_change_the_result(self):
        flame = sn.build_recipe("fire_flame", {"color": [0.1, 0.2, 1.0, 1.0], "strength": 3, "scale": 6})
        em = next(n for n in flame.nodes if n.id == "em")
        noise = next(n for n in flame.nodes if n.id == "noise")
        self.assertEqual((em.inputs["Color"], em.inputs["Strength"], noise.inputs["Scale"]), ([0.1, 0.2, 1.0, 1.0], 3.0, 6.0))
        self.assertEqual(sn.build_recipe("glass", {"ior": 1.6}).nodes[1].inputs["IOR"], 1.6)
        self.assertEqual(sn.build_recipe("car_paint", {"color": [0, 0, 1, 1]}).nodes[1].inputs["Base Color"], [0, 0, 1, 1])
        self.assertEqual(sn.build_recipe("glow", {"strength": 40}).nodes[1].inputs["Strength"], 40.0)

    def test_recipes_with_the_right_render_settings(self):
        self.assertEqual(sn.build_recipe("fire_flame").settings["surface_render_method"], "DITHERED")        # transparent hisse ke liye zaroori
        self.assertEqual(sn.build_recipe("glass").settings["surface_render_method"], "DITHERED")
        self.assertTrue(any(n.type == "VolumePrincipled" for n in sn.build_recipe("smoke_volume").nodes))
        self.assertTrue(any(l[2] == "out" and l[3] == "Volume" for l in sn.build_recipe("smoke_volume").links))
        self.assertTrue(any(n.type == "Principled" and n.inputs.get("Coat Weight") == 1.0 for n in sn.build_recipe("car_paint").nodes))

    def test_unknown_recipe_lists_the_valid_ones(self):
        with self.assertRaises(ValueError) as ctx:
            sn.build_recipe("unobtainium")
        self.assertIn("fire_flame", str(ctx.exception))
        self.assertIn("car_paint", sn.recipe_help())
        self.assertEqual(sn.build_recipe("Fire Flame").nodes[0].type, "OutputMaterial")         # naam lenient


# ----------------------------------------------------------------------------- the real bridge code against a fake node tree
class TestBridgeBuild(BridgeCase):

    def test_every_recipe_builds_a_connected_graph(self):
        for name in sn.RECIPES:
            result, material = self.build(f"M_{name}", *self.parts(name))
            self.assertEqual(result["nodes"], len(material.node_tree.nodes), name)
            self.assertEqual(len(material.node_tree.links), result["links"], name)
            output = next(n for n in material.node_tree.nodes if n.short == "OutputMaterial")
            self.assertTrue(any(inp.name in ("Surface", "Volume") for _, inp in material.node_tree.links if inp in output.inputs), name)

    @staticmethod
    def parts(name):
        spec = sn.RECIPES[name][0]({})
        return spec["nodes"], spec["links"], spec.get("settings")

    def test_values_ramps_and_props_are_applied(self):
        result, material = self.build("Flame", *self.parts("fire_flame"))
        nodes = {n.name: n for n in material.node_tree.nodes}
        self.assertEqual(nodes["em"].inputs[1].default_value, 8.0)                       # Strength
        self.assertEqual(list(nodes["em"].inputs[0].default_value), [1.0, 0.12, 0.005, 1.0])
        ramp = nodes["ramp"].color_ramp.elements
        self.assertEqual([round(e.position, 2) for e in ramp], [0.3, 0.75])
        self.assertEqual(list(ramp[1].color), [1, 1, 1, 1])
        self.assertEqual(nodes["noise"].noise_dimensions, "3D")
        self.assertEqual(nodes["shape"].operation, "MULTIPLY")
        self.assertEqual(material.surface_render_method, "DITHERED")
        self.assertFalse(material.use_backface_culling)
        self.assertEqual(nodes["map"].inputs[3].default_value, [1.0, 1.0, 0.6])        # Scale vector

    def test_numbered_sockets_reach_the_right_slot_of_mix_shader(self):
        _, material = self.build("Flame", *self.parts("fire_flame"))
        mix = next(n for n in material.node_tree.nodes if n.name == "mix")
        wired = {inp: out.name for out, inp in material.node_tree.links if inp in mix.inputs}
        self.assertEqual(wired[mix.inputs[1]], "BSDF")                                       # Transparent -> slot 1
        self.assertEqual(wired[mix.inputs[2]], "Emission")                                   # Emission -> slot 2
        self.assertEqual(wired[mix.inputs[0]], "Value")                                      # Fac <- Math

    def test_extra_ramp_stops_are_created_and_surplus_removed(self):
        nodes = [{"id": "out", "type": "OutputMaterial"}, {"id": "r", "type": "ValToRGB", "ramp": [[0, [0, 0, 0]], [0.4, [1, 0, 0]], [0.7, [1, 1, 0]], [1, [1, 1, 1]]]}]
        _, material = self.build("Ramp4", nodes, [])
        self.assertEqual([round(e.position, 2) for e in material.node_tree.nodes[1].color_ramp.elements], [0, 0.4, 0.7, 1])

    def test_rebuilding_replaces_the_old_graph(self):
        self.build("Same", *self.parts("glow"))
        first_count = len(self.bpy.data.materials.get("Same").node_tree.nodes)
        _, material = self.build("Same", *self.parts("fire_flame"))
        self.assertGreater(len(material.node_tree.nodes), first_count)
        self.assertEqual(len(self.bpy.data.materials.items), 1)

    def test_image_textures_are_loaded_with_the_right_colorspace(self):
        nodes = [{"id": "out", "type": "OutputMaterial"}, {"id": "t", "type": "TexImage", "image": "C:/tex/rough.png", "colorspace": "Non-Color"}]
        _, material = self.build("Img", nodes, [])
        image = material.node_tree.nodes[1].image
        self.assertEqual((image.filepath, image.colorspace_settings.name), ("C:/tex/rough.png", "Non-Color"))

    def test_scalar_to_vector_and_colour_padding(self):
        nodes = [{"id": "out", "type": "OutputMaterial"}, {"id": "m", "type": "Mapping", "inputs": {"Scale": 2}},
                 {"id": "e", "type": "Emission", "inputs": {"Color": [1, 0.5, 0.2]}}]
        _, material = self.build("Pad", nodes, [])
        self.assertEqual(material.node_tree.nodes[1].inputs[3].default_value, [2.0, 2.0, 2.0])
        self.assertEqual(material.node_tree.nodes[2].inputs[0].default_value, [1, 0.5, 0.2, 1.0])

    def test_blender_side_problems_become_value_errors_with_valid_names(self):
        # Blender mein socket ka naam alag nikle to agent ko valid naam dikhte hain (taaki wo khud sudhaar sake)
        spec = sn.parse_material_spec([{"id": "out", "type": "OutputMaterial"}, {"id": "n", "type": "TexNoise"}], [])
        for node in spec.nodes:
            pass
        node = FakeNode("ShaderNodeTexNoise")
        node.inputs.pop(0)                                                                # is Blender mein 'Vector' socket nahi
        original = FakeNodes.new

        def odd_new(self_, idname):
            made = original(self_, idname)
            if idname == "ShaderNodeTexNoise":
                made.inputs = [s for s in made.inputs if s.name != "Scale"]
            return made
        with mock.patch.object(FakeNodes, "new", odd_new):
            bad = sn.parse_material_spec([{"id": "out", "type": "OutputMaterial"}, {"id": "n", "type": "TexNoise", "inputs": {"Scale": 3}}], [])
            with self.assertRaises(ValueError) as ctx:
                self.bridge.build_node_material("Bad", bad)
        self.assertIn("no input socket 'Scale'", str(ctx.exception))
        self.assertIn("Available: [", str(ctx.exception))
        with mock.patch.object(sn, "NODE_TYPES", dict(sn.NODE_TYPES, Ghost="ShaderNodeDoesNotExist")):
            ghost = sn.parse_material_spec([{"id": "out", "type": "OutputMaterial"}, {"id": "g", "type": "Ghost"}], [])
            with mock.patch.object(FakeNode, "__init__", lambda self_, idname: None):
                with self.assertRaises(ValueError) as ctx:
                    self.bridge.build_node_material("Ghost", ghost)
        self.assertIn("has no node 'ShaderNodeDoesNotExist'", str(ctx.exception))

    def test_wrong_property_value_is_reported(self):
        nodes = [{"id": "out", "type": "OutputMaterial"}, {"id": "m", "type": "Math", "props": {"operation": "MULTIPLY"}}]
        spec = sn.parse_material_spec(nodes, [])

        class Strict(FakeNode):
            def __setattr__(self_, key, value):
                if key == "operation" and value == "MULTIPLY":
                    raise TypeError("enum 'MULTIPLY' not found in ('ADD',)")
                super().__setattr__(key, value)
        with mock.patch.object(blender_bridge, "bpy", self.bpy), mock.patch.object(FakeNodes, "new", lambda s, idname: s.append(Strict(idname)) or s[-1]):
            with self.assertRaises(ValueError) as ctx:
                self.bridge.build_node_material("StrictMat", spec)
        self.assertIn("cannot set operation='MULTIPLY'", str(ctx.exception))


# ----------------------------------------------------------------------------- tools
class ToolBridge(FakeBridge):
    def __init__(self):
        super().__init__()
        self.built = []
        self.render_calls = []

    def build_node_material(self, name, spec, replace=True):
        self.built.append((name, spec, replace))
        return {"name": name, "nodes": len(spec.nodes), "links": len(spec.links), "notes": []}

    def assign_material(self, object_name, material_name):
        obj = self.get_object(object_name)
        if obj is None:
            return False
        obj.material_name = material_name
        return True

    def setup_render(self, **options):
        self.render_calls.append(options)
        return {"changed": {k: v for k, v in options.items()}, "notes": []}


class TestTools(unittest.TestCase):

    def setUp(self):
        self.bridge = ToolBridge()
        self.bridge._objects.append(FakeObject(name="Flame0"))

    def test_recipe_tool_builds_and_assigns(self):
        result = MaterialRecipeTool(self.bridge).execute({"name": "Fire", "recipe": "fire_flame", "params": {"strength": 12}, "assign_to": ["Flame0", "Missing"]})
        self.assertTrue(result.success, result.error)
        self.assertEqual((result.data["recipe"], result.data["assigned_to"], result.data["not_found"]), ("fire_flame", ["Flame0"], ["Missing"]))
        self.assertEqual(self.bridge.get_object("Flame0").material_name, "Fire")
        built_spec = self.bridge.built[0][1]
        self.assertEqual(next(n for n in built_spec.nodes if n.id == "em").inputs["Strength"], 12.0)

    def test_recipe_tool_input_is_lenient_and_strict_where_it_matters(self):
        ok = MaterialRecipeInput(name="x", recipe="Rough Stone", params=None, assign_to="A, B")
        self.assertEqual(ok.assign_to, ["A", "B"])
        for bad in ({"name": "", "recipe": "glass"}, {"name": "x", "recipe": "nope"}, {"name": "x", "recipe": "glass", "params": "text"}):
            self.assertFalse(MaterialRecipeTool(self.bridge).execute(bad).success, str(bad))
        result = MaterialRecipeTool(self.bridge).execute({"name": "x", "recipe": "nope"})
        self.assertIn("Recipes:", result.error)

    def test_nodes_tool_validates_before_touching_blender(self):
        good = {"name": "Custom", "nodes": [{"id": "out", "type": "OutputMaterial"}, {"id": "e", "type": "Emission"}], "links": [["e.Emission", "out.Surface"]],
                "assign_to": ["Flame0"], "settings": {"surface_render_method": "BLENDED"}}
        result = MaterialNodesTool(self.bridge).execute(good)
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["assigned_to"], ["Flame0"])
        self.assertEqual(self.bridge.built[0][2], True)
        bad = MaterialNodesTool(self.bridge).execute(dict(good, links=[["e.Emmision", "out.Surface"]]))
        self.assertFalse(bad.success)
        self.assertIn("Outputs: Emission", bad.error)
        self.assertEqual(len(self.bridge.built), 1)                                       # galat spec bridge tak pahunchi hi nahi

    def test_blender_side_errors_come_back_as_failures(self):
        class Refusing(ToolBridge):
            def build_node_material(self, name, spec, replace=True):
                raise ValueError("n: no input socket 'Scale'. Available: ['Vector']")
        result = MaterialRecipeTool(Refusing()).execute({"name": "x", "recipe": "glass"})
        self.assertFalse(result.success)
        self.assertIn("Available: ['Vector']", result.error)

    def test_descriptions_guide_the_llm(self):
        recipe = MaterialRecipeTool(self.bridge).description
        for word in ("fire_flame", "car_paint", "smoke_volume", "light.create", "EVERY main surface"):
            self.assertIn(word, recipe)
        nodes = MaterialNodesTool(self.bridge).description
        for word in ("MixShader", "NUMBER", "DITHERED", "OutputMaterial", "Principled inputs"):
            self.assertIn(word, nodes)
        self.assertIn("LAST", RenderSetupTool(self.bridge).description)


class TestRenderSetup(unittest.TestCase):

    def test_presets_and_overrides(self):
        bridge = ToolBridge()
        result = RenderSetupTool(bridge).execute({"preset": "night", "focus_object": "Flame0", "exposure": "0.8"})
        self.assertTrue(result.success, result.error)
        options = bridge.render_calls[0]
        self.assertEqual((options["view_transform"], options["dof"], options["focus_object"], options["exposure"]), ("AgX", True, "Flame0", 0.8))
        self.assertEqual(options["world_color"], [0.003, 0.005, 0.009])                     # preset ka world (night)
        self.assertEqual(result.data["preset"], "night")
        RenderSetupTool(bridge).execute({"preset": "cinematic", "dof": False, "engine": "cycles", "samples": 64})
        second = bridge.render_calls[1]
        self.assertEqual((second["dof"], second["engine"], second["samples"]), (False, "cycles", 64))
        self.assertNotIn("world_color", second)                                              # cinematic world nahi chhedta
        self.assertEqual(set(PRESETS), {"cinematic", "product", "outdoor", "night", "clean"})

    def test_bad_input(self):
        tool = RenderSetupTool(ToolBridge())
        for bad in ({}, {"preset": "disco"}, {"engine": "luxcore"}, {"samples": 0}, {"resolution_x": 1920}, {"world_color": [1, 2]}):
            self.assertFalse(tool.execute(bad).success, str(bad))
        self.assertTrue(tool.execute({"resolution_x": "1920", "resolution_y": 1080}).success)
        self.assertEqual(RenderSetupInput(world_color="0.1, 0.2, 0.3").world_color, [0.1, 0.2, 0.3])


# ----------------------------------------------------------------------------- bridge.setup_render against a fake scene
class Enum:
    def __init__(self, *ids):
        self.bl_rna = SimpleNamespace(properties={"engine": SimpleNamespace(enum_items=[SimpleNamespace(identifier=i) for i in ids]),
                                                  "view_transform": SimpleNamespace(enum_items=[SimpleNamespace(identifier=i) for i in ids]),
                                                  "look": SimpleNamespace(enum_items=[SimpleNamespace(identifier=i) for i in ids])})


class FakeRender(Enum):
    def __init__(self):
        super().__init__("BLENDER_EEVEE", "CYCLES")
        self.engine, self.resolution_x, self.resolution_y, self.resolution_percentage, self.film_transparent = "CYCLES", 1920, 1080, 50, False


class FakeViewSettings(Enum):
    def __init__(self):
        super().__init__("AgX", "Standard", "None", "AgX - Medium High Contrast", "AgX - Punchy")
        self.view_transform, self.look, self.exposure = "Standard", "None", 0.0


class TestBridgeSetupRender(BridgeCase):

    def make_scene(self, with_camera=True):
        camera = SimpleNamespace(type="CAMERA", data=SimpleNamespace(dof=SimpleNamespace(use_dof=False, aperture_fstop=5.6, focus_object=None))) if with_camera else None
        background = SimpleNamespace(inputs={"Color": SimpleNamespace(default_value=[0, 0, 0, 1]), "Strength": SimpleNamespace(default_value=1.0)})
        world = SimpleNamespace(node_tree=SimpleNamespace(nodes=SimpleNamespace(get=lambda n: background)))
        scene = SimpleNamespace(render=FakeRender(), view_settings=FakeViewSettings(), camera=camera, world=world,
                                cycles=SimpleNamespace(samples=1, use_denoising=False), eevee=SimpleNamespace(taa_render_samples=1))
        self.bpy.context = SimpleNamespace(scene=scene)
        self.bpy.data.objects = SimpleNamespace(get=lambda n: SimpleNamespace(name=n) if n == "Flame" else None)
        return scene, background

    def test_cinematic_night_applies_everything_this_blender_supports(self):
        scene, background = self.make_scene()
        options = dict(PRESETS["night"], focus_object="Flame", samples=48, resolution_x=1080, resolution_y=1350)
        result = self.bridge.setup_render(**options)
        self.assertEqual(scene.render.engine, "BLENDER_EEVEE")
        self.assertEqual(scene.view_settings.view_transform, "AgX")
        self.assertEqual(scene.view_settings.look, "AgX - Medium High Contrast")           # 'Medium High Contrast' -> prefix ke saath mila
        self.assertEqual(scene.view_settings.exposure, 0.3)
        self.assertEqual((scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage), (1080, 1350, 100))
        self.assertEqual(scene.eevee.taa_render_samples, 48)
        cam = scene.camera.data.dof
        self.assertEqual((cam.use_dof, cam.aperture_fstop, cam.focus_object.name), (True, 2.2, "Flame"))
        self.assertEqual(background.inputs["Color"].default_value, [0.003, 0.005, 0.009, 1.0])
        self.assertEqual(background.inputs["Strength"].default_value, 0.08)
        self.assertEqual(result["notes"], [])

    def test_missing_things_are_reported_not_fatal(self):
        scene, _ = self.make_scene(with_camera=False)
        result = self.bridge.setup_render(engine="eevee", view_transform="Filmic", look="Super Punchy", dof=True, focus_object="Nothing", exposure=1.0)
        notes = " | ".join(result["notes"])
        self.assertIn("view transform 'Filmic' not available", notes)
        self.assertIn("look 'Super Punchy' not available", notes)
        self.assertIn("no camera", notes)
        self.assertEqual(scene.view_settings.view_transform, "Standard")                  # jo mila nahi use chheda nahi
        self.assertEqual(result["changed"]["exposure"], 1.0)
        scene, _ = self.make_scene()
        notes2 = self.bridge.setup_render(dof=True, focus_object="Nothing")["notes"]
        self.assertIn("focus object 'Nothing' not found", " | ".join(notes2))

    def test_cycles_samples_and_denoise(self):
        scene, _ = self.make_scene()
        self.bridge.setup_render(engine="cycles", samples=96, denoise=True, film_transparent=True)
        self.assertEqual((scene.render.engine, scene.cycles.samples, scene.cycles.use_denoising, scene.render.film_transparent), ("CYCLES", 96, True, True))


if __name__ == "__main__":
    unittest.main()