"""
BlenderBridge
=============
Hinglish: Ye class Blender ke saare raw `bpy` calls ko encapsulate karti hai.

OOP Principle: ENCAPSULATION
- Poore project mein kahin bhi directly `bpy.data`, `bpy.ops`, `bpy.context`
  nahi likhenge (sirf yahan, is file ke andar).
"""

import bpy


class BlenderBridge:
    """Blender ke saath saara low-level interaction is class ke through hoga."""

    # ---------------------------------------------------------
    # Scene level
    # ---------------------------------------------------------
    def get_scene(self):
        return bpy.context.scene

    def get_scene_name(self) -> str:
        return self.get_scene().name

    # ---------------------------------------------------------
    # Object level — read
    # ---------------------------------------------------------
    def get_objects(self):
        return list(bpy.data.objects)

    def get_object(self, name: str):
        return bpy.data.objects.get(name)

    # ---------------------------------------------------------
    # Object level — write
    # ---------------------------------------------------------
    def create_object(self, name: str, object_type: str = "MESH", primitive: str = "CUBE", location=None):
        """Naya object banata hai. Phase 2 mein `location` bhi accept karta hai."""
        if object_type == "MESH" and primitive == "CUBE":
            bpy.ops.mesh.primitive_cube_add()
        elif object_type == "MESH" and primitive == "SPHERE":
            bpy.ops.mesh.primitive_uv_sphere_add()
        else:
            raise ValueError(f"Unsupported object_type/primitive: {object_type}/{primitive}")

        obj = bpy.context.active_object
        obj.name = name

        if location is not None:
            obj.location = location

        return obj

    def delete_object(self, name: str) -> bool:
        """Naam se object delete karta hai. Success/failure bool return karta hai."""
        obj = self.get_object(name)
        if obj is None:
            return False
        bpy.data.objects.remove(obj, do_unlink=True)
        return True

    def duplicate_object(self, name: str, new_name: str = None):
        """
        Object ko duplicate karta hai. Agar new_name diya hai toh
        naye object ka naam wahi set hoga, warna Blender ka default
        naming (Cube.001) use hoga.
        """
        obj = self.get_object(name)
        if obj is None:
            return None

        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.duplicate()

        new_obj = bpy.context.active_object
        if new_name:
            new_obj.name = new_name

        return new_obj

    def rename_object(self, old_name: str, new_name: str):
        """Object ka naam change karta hai. Nahi mila toh None."""
        obj = self.get_object(old_name)
        if obj is None:
            return None
        obj.name = new_name
        return obj

    def transform_object(self, name: str, location=None, rotation=None, scale=None):
        """
        Object ki location/rotation/scale update karta hai. Sirf
        diye gaye fields update honge, baaki jaise the waise rahenge.
        """
        obj = self.get_object(name)
        if obj is None:
            return None

        if location is not None:
            obj.location = location
        if rotation is not None:
            obj.rotation_euler = rotation
        if scale is not None:
            obj.scale = scale

        return obj