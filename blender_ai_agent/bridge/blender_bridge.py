"""
BlenderBridge
=============
Hinglish: Ye class Blender ke saare raw `bpy` calls ko encapsulate karti hai.

PATCHED (thread-safety fix): Copilot ka worker thread (ui/panel.py mein
AIAGENT_OT_copilot_submit) LLM se baat background thread pe karta hai,
aur phir har tool call yahin BlenderBridge tak pahunchta hai — lekin
WORKER THREAD SE HI. bpy ka poora API sirf MAIN THREAD pe safe hai;
worker thread se seedha bpy.ops.* chalane par Blender crash ho sakta
hai (ACCESS_VIOLATION, depsgraph ke andar mesh_copy_data jaisi jagah
pe race condition — bilkul wahi crash jo bina is fix ke aata tha).

Fix: har method jo bpy ko chhuti hai, uske andar ka actual kaam ek
chhoti closure mein wrap karke `run_on_main_thread()` ko de dete hain.
Agar hum already main thread pe hain (jaise unit tests, jahan koi
threading involved nahi), `run_on_main_thread` seedha call kar deta
hai — koi extra overhead nahi. Agar worker thread se aaya hai, to
Blender ke modal-operator timer tick tak wait karta hai aur wahin
(main thread pe) safely execute hota hai.
"""

import bpy

from .main_thread_dispatch import run_on_main_thread


class BlenderBridge:
    """Blender ke saath saara low-level interaction is class ke through hoga."""

    # ---------------------------------------------------------
    # Scene level
    # ---------------------------------------------------------
    def get_scene(self):
        return run_on_main_thread(lambda: bpy.context.scene)

    def get_scene_name(self) -> str:
        return run_on_main_thread(lambda: bpy.context.scene.name)

    # ---------------------------------------------------------
    # Object level — read
    # ---------------------------------------------------------
    def get_objects(self):
        return run_on_main_thread(lambda: list(bpy.data.objects))

    def get_object(self, name: str):
        return run_on_main_thread(lambda: bpy.data.objects.get(name))

    # ---------------------------------------------------------
    # Object level — write
    # ---------------------------------------------------------
    # Hinglish: Har object_type category ke apne primitives hain, jo
    # Blender ke "Shift+A -> Add" menu ke operators se map hote hain.
    # Ek dict of dicts: {object_type: {primitive: (module, op_name)}}.
    # Wahi operators jo Blender khud use karta hai - koi "hidden" shape
    # nahi hai.
    _CREATE_OPS = {
        "MESH": {
            "CUBE": ("mesh", "primitive_cube_add"),
            "SPHERE": ("mesh", "primitive_uv_sphere_add"),
            "ICOSPHERE": ("mesh", "primitive_ico_sphere_add"),
            "CONE": ("mesh", "primitive_cone_add"),
            "CYLINDER": ("mesh", "primitive_cylinder_add"),
            "CIRCLE": ("mesh", "primitive_circle_add"),
            "PLANE": ("mesh", "primitive_plane_add"),
            "TORUS": ("mesh", "primitive_torus_add"),
            "GRID": ("mesh", "primitive_grid_add"),
            "MONKEY": ("mesh", "primitive_monkey_add"),
        },
        "CURVE": {
            "BEZIER": ("curve", "primitive_bezier_curve_add"),
            "CIRCLE": ("curve", "primitive_bezier_circle_add"),
            "NURBS_CURVE": ("curve", "primitive_nurbs_curve_add"),
            "NURBS_CIRCLE": ("curve", "primitive_nurbs_circle_add"),
            "PATH": ("curve", "primitive_nurbs_path_add"),
        },
        "SURFACE": {
            "NURBS_CURVE": ("surface", "primitive_nurbs_surface_curve_add"),
            "NURBS_CIRCLE": ("surface", "primitive_nurbs_surface_circle_add"),
            "NURBS_SURFACE": ("surface", "primitive_nurbs_surface_surface_add"),
            "NURBS_CYLINDER": ("surface", "primitive_nurbs_surface_cylinder_add"),
            "NURBS_SPHERE": ("surface", "primitive_nurbs_surface_sphere_add"),
            "NURBS_TORUS": ("surface", "primitive_nurbs_surface_torus_add"),
        },
        "METABALL": {
            "BALL": ("object", "metaball_add"),
            "CAPSULE": ("object", "metaball_add"),
            "PLANE": ("object", "metaball_add"),
            "ELLIPSOID": ("object", "metaball_add"),
            "CUBE": ("object", "metaball_add"),
        },
        "EMPTY": {
            "PLAIN_AXES": ("object", "empty_add"),
            "ARROWS": ("object", "empty_add"),
            "SINGLE_ARROW": ("object", "empty_add"),
            "CIRCLE": ("object", "empty_add"),
            "CUBE": ("object", "empty_add"),
            "SPHERE": ("object", "empty_add"),
            "CONE": ("object", "empty_add"),
        },
        "LIGHT": {
            "POINT": ("object", "light_add"),
            "SUN": ("object", "light_add"),
            "SPOT": ("object", "light_add"),
            "AREA": ("object", "light_add"),
        },
        "ARMATURE": {
            "ARMATURE": ("object", "armature_add"),
        },
        "LATTICE": {
            "LATTICE": ("object", "add"),   # bpy.ops.object.add(type='LATTICE')
        },
    }
    # 'object.metaball_add' / 'object.empty_add' / 'object.light_add' need a
    # `type=` kwarg (Blender's own enum) rather than a distinct op per shape.
    _TYPE_KWARG_ENUM = {
        "METABALL": {"BALL": "BALL", "CAPSULE": "CAPSULE", "PLANE": "PLANE",
                     "ELLIPSOID": "ELLIPSOID", "CUBE": "CUBE"},
        "EMPTY": {"PLAIN_AXES": "PLAIN_AXES", "ARROWS": "ARROWS",
                  "SINGLE_ARROW": "SINGLE_ARROW", "CIRCLE": "CIRCLE",
                  "CUBE": "CUBE", "SPHERE": "SPHERE", "CONE": "CONE"},
        "LIGHT": {"POINT": "POINT", "SUN": "SUN", "SPOT": "SPOT", "AREA": "AREA"},
    }

    def create_object(self, name: str, object_type: str = "MESH", primitive: str = "CUBE", location=None):
        """Naya object banata hai. Supports MESH/CURVE/SURFACE/METABALL/EMPTY/LIGHT/ARMATURE/LATTICE."""
        object_type = (object_type or "MESH").upper()
        primitive = (primitive or "CUBE").upper()

        category = self._CREATE_OPS.get(object_type)
        if category is None:
            raise ValueError(
                f"Unsupported object_type: {object_type}. "
                f"Supported: {', '.join(sorted(self._CREATE_OPS))}"
            )
        if primitive not in category:
            raise ValueError(
                f"Unsupported primitive '{primitive}' for object_type '{object_type}'. "
                f"Supported: {', '.join(sorted(category))}"
            )

        module_name, op_name = category[primitive]

        def _do():
            op_module = getattr(bpy.ops, module_name)
            op = getattr(op_module, op_name)

            kwarg_enum = self._TYPE_KWARG_ENUM.get(object_type)
            if kwarg_enum is not None:
                op(type=kwarg_enum[primitive])
            elif object_type == "LATTICE":
                op(type="LATTICE")
            else:
                op()

            obj = bpy.context.view_layer.objects.active
            obj.name = name

            if location is not None:
                obj.location = location

            return obj

        return run_on_main_thread(_do)

    def delete_object(self, name: str) -> bool:
        def _do():
            obj = bpy.data.objects.get(name)
            if obj is None:
                return False
            bpy.data.objects.remove(obj, do_unlink=True)
            return True

        return run_on_main_thread(_do)

    def duplicate_object(self, name: str, new_name: str = None):
        def _do():
            obj = bpy.data.objects.get(name)
            if obj is None:
                return None

            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.duplicate()

            new_obj = bpy.context.view_layer.objects.active
            if new_name:
                new_obj.name = new_name

            return new_obj

        return run_on_main_thread(_do)

    def rename_object(self, old_name: str, new_name: str):
        def _do():
            obj = bpy.data.objects.get(old_name)
            if obj is None:
                return None
            obj.name = new_name
            return obj

        return run_on_main_thread(_do)

    def transform_object(self, name: str, location=None, rotation=None, scale=None):
        def _do():
            obj = bpy.data.objects.get(name)
            if obj is None:
                return None

            if location is not None:
                obj.location = location
            if rotation is not None:
                obj.rotation_euler = rotation
            if scale is not None:
                obj.scale = scale

            return obj

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Material level — Step 2.5
    # ---------------------------------------------------------
    def get_material(self, name: str):
        return run_on_main_thread(lambda: bpy.data.materials.get(name))

    def create_material(self, name: str, color=None):
        def _do():
            material = bpy.data.materials.new(name=name)
            material.use_nodes = True

            if color is not None:
                self._set_material_base_color(material, color)

            return material

        return run_on_main_thread(_do)

    def assign_material(self, object_name: str, material_name: str):
        def _do():
            obj = bpy.data.objects.get(object_name)
            material = bpy.data.materials.get(material_name)

            if obj is None or material is None:
                return False

            if obj.data.materials:
                obj.data.materials[0] = material
            else:
                obj.data.materials.append(material)

            return True

        return run_on_main_thread(_do)

    def modify_material(self, name: str, color=None, roughness=None, metallic=None):
        def _do():
            material = bpy.data.materials.get(name)
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

        return run_on_main_thread(_do)

    def _get_principled_bsdf(self, material):
        """Hinglish: Ye sirf node data padhta hai, bpy.ops nahi chalata —
        isliye main-thread-safe caller ke andar hi use hota hai, isse
        khud alag se wrap karne ki zaroorat nahi (already run_on_main_thread
        ke andar call hota hai)."""
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
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return None
            return obj.modifiers.new(name=modifier_name, type=modifier_type)

        return run_on_main_thread(_do)

    def remove_modifier(self, object_name: str, modifier_name: str) -> bool:
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return False

            modifier = obj.modifiers.get(modifier_name)
            if modifier is None:
                return False

            obj.modifiers.remove(modifier)
            return True

        return run_on_main_thread(_do)

    def configure_modifier(self, object_name: str, modifier_name: str, properties: dict):
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return None

            modifier = obj.modifiers.get(modifier_name)
            if modifier is None:
                return None

            for key, value in properties.items():
                if hasattr(modifier, key):
                    setattr(modifier, key, value)

            return modifier

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Camera / Render level — Step 2.7
    # ---------------------------------------------------------
    def create_camera(self, name: str, location=None, rotation=None):
        """Naya camera object banata hai scene mein."""

        def _do():
            camera_data = bpy.data.cameras.new(name=f"{name}_data")
            camera_obj = bpy.data.objects.new(name=name, object_data=camera_data)
            bpy.context.collection.objects.link(camera_obj)

            if location is not None:
                camera_obj.location = location
            if rotation is not None:
                camera_obj.rotation_euler = rotation

            return camera_obj

        return run_on_main_thread(_do)

    def set_active_camera(self, name: str) -> bool:
        """Scene ka active/render camera set karta hai."""

        def _do():
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != 'CAMERA':
                return False

            bpy.context.scene.camera = obj
            return True

        return run_on_main_thread(_do)

    def render_preview(self, filepath: str) -> str:
        """
        Current scene ka render leta hai aur diye gaye filepath pe
        save karta hai. Agar path invalid/inaccessible ho (jaise
        root C:\\), safe temp folder mein fallback karta hai.
        """
        import os
        import tempfile

        directory = os.path.dirname(filepath)
        if not directory or not os.access(directory if os.path.isdir(directory) else tempfile.gettempdir(), os.W_OK):
            filename = os.path.basename(filepath) or "preview.png"
            filepath = os.path.join(tempfile.gettempdir(), filename)

        def _do():
            scene = bpy.context.scene
            scene.render.filepath = filepath
            bpy.ops.render.render(write_still=True)
            return filepath

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Geometry Nodes — Step 9.8
    # ---------------------------------------------------------
    def add_geometry_nodes(self, object_name: str, node_group_name: str):
        """Object pe naya Geometry Nodes modifier add karta hai."""

        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return None

            node_tree = bpy.data.node_groups.new(name=node_group_name, type='GeometryNodeTree')
            modifier = obj.modifiers.new(name=node_group_name, type='NODES')
            modifier.node_group = node_tree
            return modifier

        return run_on_main_thread(_do)

    def get_geometry_nodes(self, object_name: str, modifier_name: str):
        """Object ke Geometry Nodes modifier ko dhundta hai."""

        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return None
            return obj.modifiers.get(modifier_name)

        return run_on_main_thread(_do)
    # ---------------------------------------------------------
    # Geometry QA — Step 12.7
    # ---------------------------------------------------------
    def get_mesh_stats(self, object_name: str):
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None or obj.type != "MESH":
                return None

            import bmesh
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bm.normal_update()

            non_manifold_edge_count = sum(1 for edge in bm.edges if not edge.is_manifold)

            flipped_normal_count = 0
            try:
                if bm.calc_volume(signed=True) < 0:
                    flipped_normal_count = len(bm.faces)
            except Exception:
                flipped_normal_count = 0

            vertex_count = len(bm.verts)
            bm.free()

            world_corners = [obj.matrix_world @ corner for corner in [
                __import__("mathutils").Vector(c) for c in obj.bound_box
            ]]
            xs = [c.x for c in world_corners]
            ys = [c.y for c in world_corners]
            zs = [c.z for c in world_corners]

            return {
                "vertex_count": vertex_count,
                "non_manifold_edge_count": non_manifold_edge_count,
                "flipped_normal_count": flipped_normal_count,
                "bounding_box_min": [min(xs), min(ys), min(zs)],
                "bounding_box_max": [max(xs), max(ys), max(zs)],
            }

        return run_on_main_thread(_do)

    def recalculate_normals(self, object_name: str) -> bool:
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None or obj.type != "MESH":
                return False

            import bmesh
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            bm.to_mesh(obj.data)
            bm.free()
            obj.data.update()
            return True

        return run_on_main_thread(_do)

    
    # ---------------------------------------------------------
    # Animation — Step 9.13
    # ---------------------------------------------------------
    def insert_keyframe(self, object_name: str, frame: int, location=None):
        """Object ki current (ya di gayi) location pe keyframe insert karta hai."""

        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return False

            if location is not None:
                obj.location = location

            obj.keyframe_insert(data_path="location", frame=frame)
            return True

        return run_on_main_thread(_do)

    def get_keyframes(self, object_name: str):
        """Object ke location keyframes ki frame-number list deta hai."""

        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None or obj.animation_data is None or obj.animation_data.action is None:
                return []

            frames = set()
            for fcurve in obj.animation_data.action.fcurves:
                if fcurve.data_path == "location":
                    for keyframe_point in fcurve.keyframe_points:
                        frames.add(int(keyframe_point.co[0]))
            return sorted(frames)

        return run_on_main_thread(_do)