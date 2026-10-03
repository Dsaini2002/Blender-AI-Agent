from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.lighting_tools import CreateLightTool, SetWorldTool
from blender_ai_agent.tools.material_tools import CreateMaterialTool, ModifyMaterialTool
from blender_ai_agent.tools.models import CreateLightInput, ModifyMaterialInput, SetWorldInput
from .fakes import FakeBridge


class FakeRepeatedComposite:
    """Gemini SDK ka proto list: len/iter/index karta hai, lekin `list` NAHI hai."""

    def __init__(self, items):
        self._items = list(items)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def __getitem__(self, index):
        return self._items[index]

    def __repr__(self):
        return repr(self._items)


class FakeMapComposite:
    """Gemini SDK ka proto dict: items()/getitem karta hai, lekin `dict` NAHI hai."""

    def __init__(self, data):
        self._data = dict(data)

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


class TestGeminiProtoContainers(unittest.TestCase):
    """
    Regression for the REAL root cause: Gemini's fc.args holds proto containers, so
    'emission_color / location must be a list of numbers' fired even for [1.0, 0.4, 0.0].
    """

    def test_to_plain_converts_nested_proto_containers(self):
        from blender_ai_agent.tools.models import to_plain

        proto = FakeMapComposite({"name": "Lamp", "color": FakeRepeatedComposite([1.0, 0.4, 0.0]),
                                  "nested": FakeMapComposite({"xs": FakeRepeatedComposite([1, 2])})})
        plain = to_plain(proto)

        self.assertIsInstance(plain, dict)
        self.assertIsInstance(plain["color"], list)
        self.assertEqual(plain["color"], [1.0, 0.4, 0.0])
        self.assertEqual(plain["nested"], {"xs": [1, 2]})
        self.assertEqual(to_plain({"a": [1, (2, 3)], "b": "text", "c": None, "d": True}),
                         {"a": [1, [2, 3]], "b": "text", "c": None, "d": True})

    def test_emission_color_as_proto_list_is_accepted(self):
        data = ModifyMaterialInput(name="M", emission_color=FakeRepeatedComposite([1.0, 0.4, 0.0]),
                                   emission_strength=5.0)
        self.assertEqual(data.emission_color, [1.0, 0.4, 0.0])

    def test_light_fields_as_proto_containers_are_accepted(self):
        data = CreateLightInput(name="L", location=FakeRepeatedComposite([0, 0, 3]),
                                rotation=FakeRepeatedComposite([0, 0, 0]),
                                color=FakeRepeatedComposite([1.0, 0.5, 0.15]), energy=800.0)
        self.assertEqual(data.location, [0.0, 0.0, 3.0])
        self.assertEqual(data.color, [1.0, 0.5, 0.15])

    def test_world_color_and_xyz_proto_dict(self):
        self.assertEqual(SetWorldInput(color=FakeRepeatedComposite([0.1, 0.1, 0.3])).color, [0.1, 0.1, 0.3])
        data = CreateLightInput(name="L", location=FakeMapComposite({"x": 1, "y": 2, "z": 3}))
        self.assertEqual(data.location, [1.0, 2.0, 3.0])

    def test_gemini_provider_hands_plain_arguments_to_tools(self):
        from types import SimpleNamespace
        from blender_ai_agent.providers.gemini_provider import GeminiProvider

        fc = SimpleNamespace(name="material.modify", args=FakeMapComposite({
            "name": "Lamp", "emission_color": FakeRepeatedComposite([1.0, 0.4, 0.0]), "emission_strength": 5.0}))
        part = SimpleNamespace(function_call=fc, text=None)
        response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))],
                                   usage_metadata=None)

        provider = GeminiProvider.__new__(GeminiProvider)
        parsed = provider._parse_response(response)

        arguments = parsed.tool_calls[0].arguments
        self.assertIsInstance(arguments["emission_color"], list)
        self.assertEqual(arguments["emission_color"], [1.0, 0.4, 0.0])
        # and the tool input validates cleanly end to end
        self.assertEqual(ModifyMaterialInput(**arguments).emission_strength, 5.0)


class TestCreateLightInput(unittest.TestCase):

    def test_defaults(self):
        data = CreateLightInput(name="L")
        self.assertEqual(data.light_type, "POINT")
        self.assertEqual(data.color, [1.0, 1.0, 1.0])

    def test_type_is_case_insensitive_and_rgba_is_trimmed(self):
        data = CreateLightInput(name="L", light_type="spot", color=[1, 0.5, 0.2, 1.0])
        self.assertEqual(data.light_type, "SPOT")
        self.assertEqual(data.color, [1.0, 0.5, 0.2])

    def test_rejects_invalid_values(self):
        for kwargs in ({"light_type": "LASER"}, {"color": [2.0, 0, 0]}, {"color": [1, 1]},
                       {"energy": -1}, {"energy": 2_000_000}, {"location": [0, 0]},
                       {"rotation": [0]}, {"spot_angle": 0}, {"size": -0.1}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                CreateLightInput(name="L", **kwargs)

    def test_rejects_empty_name(self):
        with self.assertRaises(ValueError):
            CreateLightInput(name="")

    def test_accepts_llm_style_numbers_and_aliases(self):
        data = CreateLightInput(name="L", energy="800", color="1.0, 0.5, 0.15", location="[0, 0, 3]")
        self.assertEqual(data.energy, 800.0)
        self.assertEqual(data.color, [1.0, 0.5, 0.15])
        self.assertEqual(data.location, [0.0, 0.0, 3.0])

        result = CreateLightTool(FakeBridge()).execute({"name": "L", "intensity": 500, "type_of_light": "sun"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["energy"], 500)
        self.assertEqual(result.data["light_type"], "SUN")

    def test_location_and_rotation_accept_xyz_dicts(self):
        """Regression: 'CreateLightInput.location must be a list of numbers'."""
        data = CreateLightInput(name="L", location={"x": 0, "y": 1, "z": 2.5}, rotation={"X": 0, "Y": 0, "Z": 1.5})
        self.assertEqual(data.location, [0.0, 1.0, 2.5])
        self.assertEqual(data.rotation, [0.0, 0.0, 1.5])
        with self.assertRaises(ValueError):
            CreateLightInput(name="L", location={"x": 1})
        with self.assertRaises(ValueError):
            CreateLightInput(name="L", location=5)

    def test_light_and_world_colors_accept_names_too(self):
        self.assertEqual(CreateLightInput(name="L", color="orange").color, [1.0, 0.5, 0.0])
        self.assertEqual(SetWorldInput(color={"r": 0.1, "g": 0.1, "b": 0.3}).color, [0.1, 0.1, 0.3])


class TestCreateLightTool(unittest.TestCase):

    def test_creates_light_object_with_colour_and_energy(self):
        bridge = FakeBridge()
        tool = CreateLightTool(bridge)

        result = tool.execute({"name": "Fire", "light_type": "POINT", "location": [1, 2, 3],
                               "color": [1.0, 0.5, 0.15], "energy": 800})

        self.assertTrue(result.success)
        light = bridge.get_object("Fire")
        self.assertEqual(light.type, "LIGHT")
        self.assertEqual(light.light_type, "POINT")
        self.assertEqual(light.light_color, [1.0, 0.5, 0.15])
        self.assertEqual(light.light_energy, 800)
        self.assertEqual(list(light.location), [1, 2, 3])

    def test_reports_actual_name_on_collision(self):
        tool = CreateLightTool(FakeBridge())
        tool.execute({"name": "Lamp"})
        second = tool.execute({"name": "Lamp"})
        self.assertEqual(second.data["name"], "Lamp.001")

    def test_invalid_input_is_a_clean_failure(self):
        result = CreateLightTool(FakeBridge()).execute({"name": "L", "light_type": "LASER"})
        self.assertFalse(result.success)
        self.assertIn("light_type", result.error)

    def test_metadata(self):
        tool = CreateLightTool(FakeBridge())
        self.assertEqual(tool.name, "light.create")
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)


class TestSetWorldTool(unittest.TestCase):

    def test_sets_colour_and_strength(self):
        bridge = FakeBridge()
        result = SetWorldTool(bridge).execute({"color": [0.03, 0.03, 0.09], "strength": 0.3})
        self.assertTrue(result.success)
        self.assertEqual(bridge.world["color"], [0.03, 0.03, 0.09])
        self.assertEqual(bridge.world["strength"], 0.3)

    def test_partial_update_keeps_other_value(self):
        bridge = FakeBridge()
        SetWorldTool(bridge).execute({"color": [0.1, 0.2, 0.3]})
        SetWorldTool(bridge).execute({"strength": 0.5})
        self.assertEqual(bridge.world["color"], [0.1, 0.2, 0.3])
        self.assertEqual(bridge.world["strength"], 0.5)

    def test_accepts_string_numbers(self):
        data = SetWorldInput(color=["0.1", "0.2", "0.3"], strength="0.4")
        self.assertEqual(data.color, [0.1, 0.2, 0.3])
        self.assertEqual(data.strength, 0.4)

    def test_requires_something_to_set(self):
        with self.assertRaises(ValueError):
            SetWorldInput()
        self.assertFalse(SetWorldTool(FakeBridge()).execute({}).success)

    def test_rejects_bad_values(self):
        for kwargs in ({"color": [1.5, 0, 0]}, {"color": [0, 0]}, {"strength": -1}, {"strength": 500}):
            with self.assertRaises(ValueError, msg=str(kwargs)):
                SetWorldInput(**kwargs)

    def test_metadata(self):
        tool = SetWorldTool(FakeBridge())
        self.assertEqual(tool.name, "world.set")
        self.assertEqual(tool.permission, Permission.SAFE_WRITE)


class TestMaterialEmission(unittest.TestCase):

    def _bridge_with_material(self):
        bridge = FakeBridge()
        CreateMaterialTool(bridge).execute({"name": "Flame", "color": [1, 0.3, 0.1]})
        return bridge

    def test_emission_color_and_strength_are_applied(self):
        bridge = self._bridge_with_material()
        result = ModifyMaterialTool(bridge).execute(
            {"name": "Flame", "emission_color": [1.0, 0.4, 0.0], "emission_strength": 8.0})
        self.assertTrue(result.success)
        material = bridge.get_material("Flame")
        self.assertEqual(material.emission_color, [1.0, 0.4, 0.0, 1.0])
        self.assertEqual(material.emission_strength, 8.0)

    def test_emission_color_alone_gets_a_visible_default_strength(self):
        data = ModifyMaterialInput(name="Flame", emission_color=[1, 0.4, 0])
        self.assertEqual(data.emission_strength, 1.0)

    def test_emission_only_is_a_valid_modify(self):
        ModifyMaterialInput(name="M", emission_strength=3.0)  # must not raise

    def test_rejects_bad_emission_values(self):
        with self.assertRaises(ValueError):
            ModifyMaterialInput(name="M", emission_strength=-1)
        with self.assertRaises(ValueError):
            ModifyMaterialInput(name="M", emission_strength=5000)
        with self.assertRaises(ValueError):
            ModifyMaterialInput(name="M", emission_color=[1, 0])

    def test_emission_accepts_string_numbers(self):
        data = ModifyMaterialInput(name="M", emission_color=["1", "0.5", "0"], emission_strength="5")
        self.assertEqual(data.emission_color, [1.0, 0.5, 0.0])
        self.assertEqual(data.emission_strength, 5.0)

    def test_emission_color_accepts_dict_hex_and_names(self):
        self.assertEqual(ModifyMaterialInput(name="M", emission_color={"r": 1, "g": 0.5, "b": 0}).emission_color,
                         [1.0, 0.5, 0.0])
        self.assertEqual(ModifyMaterialInput(name="M", emission_color={"Red": 1, "Green": 0.5, "Blue": 0}).emission_color,
                         [1.0, 0.5, 0.0])
        self.assertEqual(ModifyMaterialInput(name="M", emission_color="orange").emission_color, [1.0, 0.5, 0.0])
        self.assertEqual(ModifyMaterialInput(name="M", emission_color="#FF8000").emission_color[:2], [1.0, 128 / 255])
        self.assertEqual(ModifyMaterialInput(name="M", emission_color="#f80").emission_color[0], 1.0)

    def test_emission_color_accepts_many_other_llm_formats(self):
        def parse(value):
            return ModifyMaterialInput(name="M", emission_color=value).emission_color

        self.assertEqual(parse("1 0.5 0"), [1.0, 0.5, 0.0])
        self.assertEqual(parse("(1.0, 0.5, 0.0)"), [1.0, 0.5, 0.0])
        self.assertEqual(parse("R:1 G:0.5 B:0"), [1.0, 0.5, 0.0])
        self.assertEqual(parse([[1, 0.5, 0]]), [1.0, 0.5, 0.0])
        self.assertEqual(parse(["orange"]), [1.0, 0.5, 0.0])
        self.assertEqual(parse("bright orange"), [1.0, 0.5, 0.0])
        self.assertEqual(parse("glowing orange light"), [1.0, 0.5, 0.0])
        self.assertEqual(parse("ORANGE"), [1.0, 0.5, 0.0])
        self.assertEqual(parse({"hex": "#FF8000"})[0], 1.0)
        self.assertEqual(parse({"rgb": [1, 0.5, 0]}), [1.0, 0.5, 0.0])
        self.assertEqual(parse("#FF8000FF")[:2], [1.0, 128 / 255])
        self.assertEqual(parse([1, 0.5, 0, 1]), [1.0, 0.5, 0.0, 1.0])
        # 0-255 scale
        self.assertEqual(parse([255, 128, 0]), [1.0, 128 / 255, 0.0])
        self.assertEqual(parse("rgb(255, 128, 0)"), [1.0, 128 / 255, 0.0])
        # HDR-ish small values are left alone
        self.assertEqual(parse([2.5, 1.0, 0.2]), [2.5, 1.0, 0.2])

    def test_bad_color_error_shows_what_was_received(self):
        with self.assertRaises(ValueError) as ctx:
            ModifyMaterialInput(name="M", emission_color={"weird": "thing"})
        self.assertIn("got {'weird': 'thing'}", str(ctx.exception))

    def test_bad_emission_color_gives_helpful_message(self):
        for bad in (5, {"x": 1}, "not-a-colour", [1, 2]):
            with self.assertRaises(ValueError, msg=str(bad)):
                ModifyMaterialInput(name="M", emission_color=bad)
        with self.assertRaises(ValueError) as ctx:
            ModifyMaterialInput(name="M", emission_color="not-a-colour")
        self.assertIn("colour name", str(ctx.exception))

    def test_nothing_to_modify_still_fails(self):
        with self.assertRaises(ValueError):
            ModifyMaterialInput(name="M")

    def test_existing_behaviour_unchanged(self):
        bridge = self._bridge_with_material()
        ModifyMaterialTool(bridge).execute({"name": "Flame", "roughness": 0.2})
        self.assertEqual(bridge.get_material("Flame").roughness, 0.2)
        self.assertEqual(bridge.get_material("Flame").emission_strength, 0.0)


if __name__ == "__main__":
    unittest.main()