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
        obj = self.get_object(name)
        if obj is None:
            return False
        bpy.data.objects.remove(obj, do_unlink=True)
        return True

    def duplicate_object(self, name: str, new_name: str = None):
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
        obj = self.get_object(old_name)
        if obj is None:
            return None
        obj.name = new_name
        return obj

    def transform_object(self, name: str, location=None, rotation=None, scale=None):
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

    # ---------------------------------------------------------
    # Material level — Step 2.5
    # ---------------------------------------------------------
    def get_material(self, name: str):
        return bpy.data.materials.get(name)

    def create_material(self, name: str, color=None):
        material = bpy.data.materials.new(name=name)
        material.use_nodes = True

        if color is not None:
            self._set_material_base_color(material, color)

        return material

    def assign_material(self, object_name: str, material_name: str):
        obj = self.get_object(object_name)
        material = self.get_material(material_name)

        if obj is None or material is None:
            return False

        if obj.data.materials:
            obj.data.materials[0] = material
        else:
            obj.data.materials.append(material)

        return True

    def modify_material(self, name: str, color=None, roughness=None, metallic=None):
        material = self.get_material(name)
        if material is None:
            return None

        if color is not None:
            self._set_material_base_color(material, color)

        bsdf = self._get_principled_bsdf(material)
        if bsdf is not None:
            if roughness is not None:
                bsdf.inputs["Roughness"].default_value = roughness
            if metallic is not None:
                bsdf.inputs["Metallic"].default_value = metallic

        return material

    def _get_principled_bsdf(self, material):
        if not material.use_nodes:
            return None
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                return node
        return None

    def _set_material_base_color(self, material, color):
        bsdf = self._get_principled_bsdf(material)
        if bsdf is not None:
            rgba = list(color) + [1.0] if len(color) == 3 else list(color)
            bsdf.inputs["Base Color"].default_value = rgba

    # ---------------------------------------------------------
    # Modifier level — Step 2.6
    # ---------------------------------------------------------
    def add_modifier(self, object_name: str, modifier_name: str, modifier_type: str = "BEVEL"):
        obj = self.get_object(object_name)
        if obj is None:
            return None

        modifier = obj.modifiers.new(name=modifier_name, type=modifier_type)
        return modifier

    def remove_modifier(self, object_name: str, modifier_name: str) -> bool:
        obj = self.get_object(object_name)
        if obj is None:
            return False

        modifier = obj.modifiers.get(modifier_name)
        if modifier is None:
            return False

        obj.modifiers.remove(modifier)
        return True

    def configure_modifier(self, object_name: str, modifier_name: str, properties: dict):
        obj = self.get_object(object_name)
        if obj is None:
            return None

        modifier = obj.modifiers.get(modifier_name)
        if modifier is None:
            return None

        for key, value in properties.items():
            if hasattr(modifier, key):
                setattr(modifier, key, value)

        return modifier

    # ---------------------------------------------------------
    # Camera / Render level — Step 2.7
    # ---------------------------------------------------------
    def create_camera(self, name: str, location=None, rotation=None):
        """Naya camera object banata hai scene mein."""
        camera_data = bpy.data.cameras.new(name=f"{name}_data")
        camera_obj = bpy.data.objects.new(name=name, object_data=camera_data)
        bpy.context.collection.objects.link(camera_obj)

        if location is not None:
            camera_obj.location = location
        if rotation is not None:
            camera_obj.rotation_euler = rotation

        return camera_obj

    def set_active_camera(self, name: str) -> bool:
        """Scene ka active/render camera set karta hai."""
        obj = self.get_object(name)
        if obj is None or obj.type != 'CAMERA':
            return False

        self.get_scene().camera = obj
        return True

    def render_preview(self, filepath: str) -> str:
        """
        Current scene ka render leta hai aur diye gaye filepath pe
        save karta hai. Path wapas return karta hai — future mein
        Vision system (Phase 5) isi image ko "dekhega".
        """
        scene = self.get_scene()
        scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)
        return filepath