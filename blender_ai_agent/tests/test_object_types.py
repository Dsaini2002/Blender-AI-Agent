from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.bridge.blender_bridge import BlenderBridge
from blender_ai_agent.tools.models import CreateObjectInput
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


if __name__ == "__main__":
    unittest.main()