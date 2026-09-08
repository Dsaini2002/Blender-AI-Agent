"""
BlenderBridge
=============
Hinglish: Ye class Blender ke saare raw `bpy` calls ko encapsulate karti hai.
"""

import bpy


class BlenderBridge:
    """Blender ke saath saara low-level interaction is class ke through hoga."""

    # ---------------------------------------------------------
    # Scene level
    # ---------------------------------------------------------
    def get_scene(self):
        """Active scene ka reference deta hai."""
        return bpy.context.scene

    def get_scene_name(self) -> str:
        return self.get_scene().name

    # ---------------------------------------------------------
    # Object level
    # ---------------------------------------------------------
    def get_objects(self):
        """Scene ke saare objects ki list deta hai (raw bpy objects)."""
        return list(bpy.data.objects)

    def get_object(self, name: str):
        """Naam se ek object dhundta hai. Nahi mila toh None."""
        return bpy.data.objects.get(name)

    def create_object(self, name: str, object_type: str = "MESH", primitive: str = "CUBE"):
        """
        Naya object banata hai. Phase 1 mein sirf CUBE/SPHERE mesh
        primitives support honge — future mein extend karenge.
        """
        if object_type == "MESH" and primitive == "CUBE":
            bpy.ops.mesh.primitive_cube_add()
        elif object_type == "MESH" and primitive == "SPHERE":
            bpy.ops.mesh.primitive_uv_sphere_add()
        else:
            raise ValueError(f"Unsupported object_type/primitive: {object_type}/{primitive}")

        obj = bpy.context.active_object
        obj.name = name
        return obj

    def delete_object(self, name: str) -> bool:
        """Naam se object delete karta hai. Success/failure bool return karta hai."""
        obj = self.get_object(name)
        if obj is None:
            return False
        bpy.data.objects.remove(obj, do_unlink=True)
        return True