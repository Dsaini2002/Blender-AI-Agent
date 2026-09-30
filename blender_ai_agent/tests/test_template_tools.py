from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.models import BuildTemplateInput
from blender_ai_agent.tools.template_tools import BuildTemplateTool
from .fakes import FakeBridge


class TestBuildTemplateInput(unittest.TestCase):

    def test_requires_template_name(self):
        with self.assertRaises(ValueError):
            BuildTemplateInput(template_name="")

    def test_colors_must_be_dict(self):
        with self.assertRaises(ValueError):
            BuildTemplateInput(template_name="humanoid", colors="red")

    def test_defaults(self):
        inp = BuildTemplateInput(template_name="humanoid")
        self.assertEqual(inp.prefix, "")
        self.assertTrue(inp.include_optional_parts)


class TestBuildTemplateToolHumanoid(unittest.TestCase):

    def test_builds_full_25_part_humanoid_with_prefix(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        result = tool.execute({"template_name": "humanoid", "prefix": "spidey_"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["part_count"], 33)
        self.assertIn("spidey_torso", result.data["created_objects"])
        self.assertIn("spidey_knee_l", result.data["created_objects"])
        self.assertIn("spidey_elbow_r", result.data["created_objects"])
        self.assertIsNotNone(bridge.get_object("spidey_torso"))

    def test_excluding_optional_parts_drops_emblem_only(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        result = tool.execute({
            "template_name": "humanoid", "prefix": "h_", "include_optional_parts": False,
        })
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["part_count"], 24)  # 33 total - 9 optional (emblem + nose/2 brows/2 ears/mouth/2 dimple cutters)
        self.assertNotIn("h_emblem", result.data["created_objects"])

    def test_torso_gets_bevel_modifier_applied(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        tool.execute({"template_name": "humanoid", "prefix": "h_"})
        obj = bridge.get_object("h_torso")
        self.assertIsNotNone(obj.modifiers.get("Bevel"))

    def test_scale_is_applied_via_transform(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        tool.execute({"template_name": "humanoid", "prefix": "h_"})
        obj = bridge.get_object("h_head")
        self.assertEqual(list(obj.scale), [0.13, 0.13, 0.13])

    def test_custom_colors_override_defaults(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        result = tool.execute({
            "template_name": "humanoid", "prefix": "h_",
            "colors": {"primary": [0.0, 1.0, 0.0, 1.0]},
        })
        self.assertTrue(result.success, result.error)
        mat = bridge.get_material("h_mat_primary")
        self.assertEqual(list(mat.color), [0.0, 1.0, 0.0, 1.0])

    def test_unknown_template_name_fails_gracefully_lists_available(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        result = tool.execute({"template_name": "does_not_exist"})
        self.assertFalse(result.success)
        self.assertIn("humanoid", result.error)


class TestBuildTemplateFaceDetail(unittest.TestCase):

    def test_nose_eyebrows_ears_mouth_are_created(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        result = tool.execute({"template_name": "humanoid", "prefix": "h_"})
        self.assertTrue(result.success, result.error)
        for part in ("h_nose", "h_eyebrow_l", "h_eyebrow_r",
                     "h_ear_l", "h_ear_r", "h_mouth"):
            self.assertIn(part, result.data["created_objects"])
            self.assertIsNotNone(bridge.get_object(part))

    def test_dimple_cutters_are_hidden_after_boolean_cut(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        result = tool.execute({"template_name": "humanoid", "prefix": "h_"})
        self.assertTrue(result.success, result.error)
        cutter = bridge.get_object("h_dimple_cutter_l")
        self.assertTrue(cutter.hide_viewport)
        self.assertTrue(cutter.hide_render)

    def test_dimple_boolean_modifier_applied_to_head(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        tool.execute({"template_name": "humanoid", "prefix": "h_"})
        head = bridge.get_object("h_head")
        modifier = head.modifiers.get("Cut_h_dimple_cutter_l")
        self.assertIsNotNone(modifier)

    def test_face_detail_excluded_when_include_optional_parts_false(self):
        bridge = FakeBridge()
        tool = BuildTemplateTool(bridge)
        result = tool.execute({
            "template_name": "humanoid", "prefix": "h_", "include_optional_parts": False,
        })
        self.assertTrue(result.success, result.error)
        for part in ("h_nose", "h_dimple_cutter_l", "h_mouth"):
            self.assertNotIn(part, result.data["created_objects"])


if __name__ == "__main__":
    unittest.main()


class TestBuildTemplateInputAcceptsJSONStringColors(unittest.TestCase):
    """Hinglish: Gemini kabhi colors ko JSON string bhejta hai (dict ki
    jagah) - crash nahi, parse ho jaana chahiye. Same pattern as
    ConfigureModifierInput.properties."""

    def test_dict_colors_pass_through_unchanged(self):
        inp = BuildTemplateInput(template_name="humanoid", colors={"primary": [0.8, 0.1, 0.1, 1.0]})
        self.assertEqual(inp.colors, {"primary": [0.8, 0.1, 0.1, 1.0]})

    def test_json_string_colors_are_parsed_to_dict(self):
        inp = BuildTemplateInput(
            template_name="humanoid",
            colors='{"primary": [0.8, 0.1, 0.1, 1.0], "secondary": [0.1, 0.2, 0.8, 1.0]}',
        )
        self.assertEqual(inp.colors, {"primary": [0.8, 0.1, 0.1, 1.0], "secondary": [0.1, 0.2, 0.8, 1.0]})

    def test_unparseable_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            BuildTemplateInput(template_name="humanoid", colors="not json")

    def test_json_string_that_is_not_an_object_raises(self):
        with self.assertRaises(ValueError):
            BuildTemplateInput(template_name="humanoid", colors="[1, 2, 3]")

    def test_none_colors_still_allowed(self):
        inp = BuildTemplateInput(template_name="humanoid", colors=None)
        self.assertIsNone(inp.colors)

    def test_non_dict_non_string_colors_raises(self):
        with self.assertRaises(ValueError):
            BuildTemplateInput(template_name="humanoid", colors=[("primary", [1, 0, 0, 1])])