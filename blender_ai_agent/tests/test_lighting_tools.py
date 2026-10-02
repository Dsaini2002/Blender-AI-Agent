from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.base import Permission
from blender_ai_agent.tools.lighting_tools import CreateLightTool, SetWorldTool
from blender_ai_agent.tools.material_tools import CreateMaterialTool, ModifyMaterialTool
from blender_ai_agent.tools.models import CreateLightInput, ModifyMaterialInput, SetWorldInput
from .fakes import FakeBridge


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
