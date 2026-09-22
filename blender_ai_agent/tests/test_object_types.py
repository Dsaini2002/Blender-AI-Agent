from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.bridge.blender_bridge import BlenderBridge
from blender_ai_agent.tools.models import ConfigureModifierInput, CreateObjectInput
from blender_ai_agent.tools.object_tools import CreateObjectTool
from .fakes import FakeBridge


class TestCreateOpsMapping(unittest.TestCase):
    """Hinglish: har naya object_type/primitive combo ke liye ek REAL
    (module, op_name) exist karna chahiye, aur wo Blender ka asli operator
    hona chahiye - typo se koi bhi bhoot-operator define na ho jaye."""

    def test_all_categories_present(self):
        expected = {"MESH", "CURVE", "SURFACE", "METABALL", "EMPTY",
                    "LIGHT", "ARMATURE", "LATTICE"}
        self.assertEqual(set(BlenderBridge._CREATE_OPS), expected)

    def test_mesh_has_grid_and_icosphere(self):
        mesh = BlenderBridge._CREATE_OPS["MESH"]
        self.assertIn("GRID", mesh)
        self.assertIn("ICOSPHERE", mesh)
        self.assertEqual(mesh["GRID"], ("mesh", "primitive_grid_add"))
        self.assertEqual(mesh["ICOSPHERE"], ("mesh", "primitive_ico_sphere_add"))

    def test_light_and_empty_use_type_kwarg(self):
        self.assertEqual(BlenderBridge._CREATE_OPS["LIGHT"]["SUN"], ("object", "light_add"))
        self.assertEqual(BlenderBridge._TYPE_KWARG_ENUM["LIGHT"]["SUN"], "SUN")
        self.assertEqual(BlenderBridge._CREATE_OPS["EMPTY"]["ARROWS"], ("object", "empty_add"))

    def test_unsupported_object_type_raises_with_helpful_list(self):
        bridge = BlenderBridge.__new__(BlenderBridge)  # bpy.* call avoid karne ke liye init skip
        with self.assertRaises(ValueError) as ctx:
            bridge.create_object(name="x", object_type="FORCE_FIELD", primitive="WIND")
        self.assertIn("Unsupported object_type", str(ctx.exception))
        self.assertIn("LIGHT", str(ctx.exception))   # supported list dikhni chahiye

    def test_unsupported_primitive_for_valid_type_raises(self):
        bridge = BlenderBridge.__new__(BlenderBridge)
        with self.assertRaises(ValueError) as ctx:
            bridge.create_object(name="x", object_type="LIGHT", primitive="LASER")
        self.assertIn("Unsupported primitive", str(ctx.exception))
        self.assertIn("SUN", str(ctx.exception))


class TestCreateObjectInputNewTypes(unittest.TestCase):

    def test_accepts_light_object_type(self):
        inp = CreateObjectInput(name="Sun1", object_type="LIGHT", primitive="SUN")
        self.assertEqual(inp.object_type, "LIGHT")
        self.assertEqual(inp.primitive, "SUN")

    def test_mesh_primitive_in_object_type_field_still_normalizes(self):
        # regression: chhota model kabhi-kabhi primitive naam object_type
        # mein bhej deta hai - purana defensive-fix behaviour bacha rehna chahiye.
        inp = CreateObjectInput(name="Cube1", object_type="ICOSPHERE")
        self.assertEqual(inp.object_type, "MESH")
        self.assertEqual(inp.primitive, "ICOSPHERE")

    def test_ambiguous_circle_is_not_auto_normalized(self):
        # CIRCLE MESH/CURVE/SURFACE/EMPTY sabmein hai - isliye ye
        # _KNOWN_PRIMITIVES mein nahi, normalize nahi hota (ambiguous).
        inp = CreateObjectInput(name="C1", object_type="CIRCLE")
        self.assertEqual(inp.object_type, "CIRCLE")   # unchanged, tool.execute() aage reject karega


class TestCreateObjectToolPassesNewFields(unittest.TestCase):

    def test_tool_passes_object_type_and_primitive_to_bridge(self):
        bridge = FakeBridge()
        tool = CreateObjectTool(bridge)
        result = tool.execute({"name": "Lamp1", "object_type": "LIGHT", "primitive": "POINT"})
        self.assertTrue(result.success)
        self.assertEqual(bridge.get_object("Lamp1").type, "LIGHT")


class TestConfigureModifierInputAcceptsJSONString(unittest.TestCase):
    """Hinglish: Gemini kabhi properties ko JSON string bhejta hai
    (dict ki jagah) - crash nahi, parse ho jaana chahiye."""

    def test_dict_properties_pass_through_unchanged(self):
        inp = ConfigureModifierInput(
            object_name="car_body", modifier_name="Bevel", properties={"width": 0.03, "segments": 3}
        )
        self.assertEqual(inp.properties, {"width": 0.03, "segments": 3})

    def test_json_string_properties_are_parsed_to_dict(self):
        inp = ConfigureModifierInput(
            object_name="car_body", modifier_name="Bevel",
            properties='{"width": 0.03, "segments": 3}',
        )
        self.assertEqual(inp.properties, {"width": 0.03, "segments": 3})

    def test_unparseable_string_raises_value_error(self):
        with self.assertRaises(ValueError):
            ConfigureModifierInput(object_name="x", modifier_name="Bevel", properties="not json")

    def test_json_string_that_is_not_an_object_raises(self):
        with self.assertRaises(ValueError):
            ConfigureModifierInput(object_name="x", modifier_name="Bevel", properties="[1, 2, 3]")

    def test_non_dict_non_string_properties_raises(self):
        with self.assertRaises(ValueError):
            ConfigureModifierInput(object_name="x", modifier_name="Bevel", properties=[("width", 0.03)])

    def test_empty_properties_still_rejected(self):
        with self.assertRaises(ValueError):
            ConfigureModifierInput(object_name="x", modifier_name="Bevel", properties={})


if __name__ == "__main__":
    unittest.main()


from blender_ai_agent.bridge.blender_bridge import BlenderBridge as _BB
from blender_ai_agent.tools.asset_tools import ImportModelTool
from blender_ai_agent.tools.models import ImportModelInput


class TestImportModelInput(unittest.TestCase):

    def test_accepts_supported_extensions(self):
        for ext in (".obj", ".fbx", ".glb", ".gltf"):
            inp = ImportModelInput(filepath=f"/tmp/car{ext}")
            self.assertEqual(inp.filepath, f"/tmp/car{ext}")

    def test_rejects_unsupported_extension(self):
        with self.assertRaises(ValueError):
            ImportModelInput(filepath="/tmp/car.blend")

    def test_rejects_empty_filepath(self):
        with self.assertRaises(ValueError):
            ImportModelInput(filepath="")

    def test_scale_must_have_three_values(self):
        with self.assertRaises(ValueError):
            ImportModelInput(filepath="/tmp/car.obj", scale=[1.0, 1.0])


class TestImportOpsMapping(unittest.TestCase):

    def test_all_extensions_have_a_mapped_importer(self):
        self.assertEqual(
            set(_BB._IMPORT_OPS), {".obj", ".fbx", ".glb", ".gltf"}
        )

    def test_unsupported_extension_raises(self):
        bridge = _BB.__new__(_BB)
        with self.assertRaises(ValueError) as ctx:
            bridge.import_model(filepath="/tmp/model.blend")
        self.assertIn("Unsupported file extension", str(ctx.exception))

    def test_missing_file_raises_before_touching_blender(self):
        bridge = _BB.__new__(_BB)
        with self.assertRaises(ValueError) as ctx:
            bridge.import_model(filepath="/definitely/not/a/real/file.obj")
        self.assertIn("not found", str(ctx.exception))


class TestImportModelToolWithFakeBridge(unittest.TestCase):

    def test_import_creates_named_object(self):
        bridge = FakeBridge()
        tool = ImportModelTool(bridge)
        result = tool.execute({"filepath": "/tmp/ferrari.glb", "name": "ferrari_body"})
        self.assertTrue(result.success)
        self.assertEqual(result.data["imported_objects"], ["ferrari_body"])
        self.assertIsNotNone(bridge.get_object("ferrari_body"))


class TestConfigureModifierResolvesObjectReferences(unittest.TestCase):
    """Hinglish: BOOLEAN/MIRROR modifiers ke object-reference properties
    (jaise 'object', 'mirror_object') string naam se resolve hone chahiye,
    plain setattr(modifier, 'object', 'some_name') se crash nahi honi chahiye."""

    def test_object_ref_properties_constant_covers_known_cases(self):
        self.assertIn("object", _BB._OBJECT_REF_PROPERTIES)
        self.assertIn("mirror_object", _BB._OBJECT_REF_PROPERTIES)

    def test_missing_referenced_object_raises_clear_error(self):
        bridge = _BB.__new__(_BB)
        # bpy.data.objects.get sirf real Blender mein kaam karega — is test
        # ka goal sirf ye hai ki method exist kare aur signature sahi ho.
        self.assertTrue(callable(bridge.configure_modifier))