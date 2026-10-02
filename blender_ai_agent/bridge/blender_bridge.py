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

    def modify_material(self, name: str, color=None, roughness=None, metallic=None,
                        emission_color=None, emission_strength=None):
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

                # Hinglish: Blender 4.x mein socket "Emission Color" hai, 3.x mein
                # "Emission" — dono versions ke liye fallback.
                if emission_color is not None:
                    rgba = list(emission_color) + [1.0] if len(emission_color) == 3 else list(emission_color)
                    socket = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
                    if socket is not None:
                        socket.default_value = rgba
                if emission_strength is not None:
                    strength_socket = bsdf.inputs.get("Emission Strength")
                    if strength_socket is not None:
                        strength_socket.default_value = float(emission_strength)

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
    # Lights + World
    # ---------------------------------------------------------
    def create_light(self, name: str, light_type: str = "POINT", location=None, rotation=None,
                     color=None, energy: float = 1000.0, size: float = 0.25, spot_angle: float = 45.0):
        """
        Hinglish: bpy.data se seedha light datablock + object banate hain
        (bpy.ops nahi) — isse selection/active-object context par depend nahi
        karna padta, aur name/colour/energy ek hi step mein set ho jaate hain.
        """
        def _do():
            import math

            light_data = bpy.data.lights.new(name=name, type=light_type)
            light_data.color = list(color)[:3] if color is not None else [1.0, 1.0, 1.0]
            light_data.energy = float(energy)

            if light_type in ("POINT", "SPOT"):
                light_data.shadow_soft_size = float(size)
            if light_type == "AREA":
                light_data.size = float(size)
            if light_type == "SPOT":
                light_data.spot_size = math.radians(float(spot_angle))

            obj = bpy.data.objects.new(name=name, object_data=light_data)
            bpy.context.collection.objects.link(obj)

            if location is not None:
                obj.location = location
            if rotation is not None:
                obj.rotation_euler = rotation

            return obj

        return run_on_main_thread(_do)

    def set_world(self, color=None, strength=None):
        """
        Hinglish: Scene ke World ka Background node set karta hai. Agar scene
        mein world hi nahi hai to naya bana deta hai, aur agar Background node
        missing hai to bana ke World Output se jod deta hai.
        """
        def _do():
            scene = bpy.context.scene
            world = scene.world
            if world is None:
                world = bpy.data.worlds.new("World")
                scene.world = world

            world.use_nodes = True
            nodes = world.node_tree.nodes
            links = world.node_tree.links

            background = next((n for n in nodes if n.type == "BACKGROUND"), None)
            if background is None:
                background = nodes.new(type="ShaderNodeBackground")
                output = next((n for n in nodes if n.type == "OUTPUT_WORLD"), None)
                if output is None:
                    output = nodes.new(type="ShaderNodeOutputWorld")
                links.new(background.outputs["Background"], output.inputs["Surface"])

            if color is not None:
                background.inputs["Color"].default_value = list(color)[:3] + [1.0]
            if strength is not None:
                background.inputs["Strength"].default_value = float(strength)

            return {
                "world": world.name,
                "color": list(background.inputs["Color"].default_value)[:3],
                "strength": float(background.inputs["Strength"].default_value),
            }

        return run_on_main_thread(_do)

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

    def set_object_visibility(self, object_name: str, hide: bool) -> bool:
        """Hinglish: Boolean-cutter objects (jinka sirf shape chahiye, khud
        wo dikhna nahi chahiye) ko viewport aur render dono se chhupata hai.
        Object delete NAHI hota - Boolean modifier ko uski mesh data
        chahiye hoti hai, isliye cutter zinda rehna zaroori hai."""
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return False
            obj.hide_viewport = hide
            obj.hide_render = hide
            return True

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

    # Hinglish: BOOLEAN modifier ka 'object' property aur MIRROR modifier
    # ka 'mirror_object' - ye dono Blender mein ek REAL bpy.types.Object
    # reference maangte hain, ek plain string naam nahi. Pehle
    # configure_modifier seedha setattr(modifier, "object", "car_cutter")
    # kar deta tha, jo silently fail ho jaata (ya crash) kyunki string
    # ek Object nahi hai. Ab jin properties ko Object chahiye unke liye
    # object naam ko real object mein resolve karte hain.
    _OBJECT_REF_PROPERTIES = {"object", "mirror_object", "target", "start_cap", "end_cap", "offset_object"}

    def configure_modifier(self, object_name: str, modifier_name: str, properties: dict):
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return None

            modifier = obj.modifiers.get(modifier_name)
            if modifier is None:
                return None

            for key, value in properties.items():
                if not hasattr(modifier, key):
                    continue
                if key in self._OBJECT_REF_PROPERTIES and isinstance(value, str):
                    resolved = bpy.data.objects.get(value)
                    if resolved is None:
                        raise ValueError(
                            f"configure_modifier: object '{value}' (for property '{key}') "
                            f"not found in scene."
                        )
                    setattr(modifier, key, resolved)
                else:
                    setattr(modifier, key, value)

            return modifier

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Camera / Render level — Step 2.7
    # ---------------------------------------------------------
    # Hinglish: Har extension ke liye Blender ka APNA built-in import
    # operator hai - ye koi third-party asset download nahi karta, sirf
    # ek file jo user ne khud disk par pehle se rakhi hai, scene mein
    # LAATA hai. .obj aur .gltf/.glb Blender mein hamesha built-in hote
    # hain; .fbx ke liye "Import-Export: FBX format" addon enabled hona
    # chahiye (zyadatar installs mein by default hota hai).
    _IMPORT_OPS = {
        ".obj": lambda filepath: bpy.ops.wm.obj_import(filepath=filepath),
        ".fbx": lambda filepath: bpy.ops.import_scene.fbx(filepath=filepath),
        ".glb": lambda filepath: bpy.ops.import_scene.gltf(filepath=filepath),
        ".gltf": lambda filepath: bpy.ops.import_scene.gltf(filepath=filepath),
    }

    def list_blend_objects(self, filepath: str):
        """Hinglish: .blend file ke ANDAR kaun-kaun se objects hain, ye
        bina kuch import kiye check karta hai - .blend files obj/fbx ki
        tarah 'poori file import karo' nahi hoti, isme se specific named
        objects CHUNNE padte hain (bpy.ops.wm.append), isliye pehle list
        dekhna zaroori hai."""
        import os
        if not os.path.isfile(filepath):
            raise ValueError(f"File not found: {filepath}")
        if not filepath.lower().endswith(".blend"):
            raise ValueError(f"list_blend_objects expects a .blend file, got: {filepath}")

        def _do():
            with bpy.data.libraries.load(filepath, link=False) as (data_from, _data_to):
                return list(data_from.objects)

        return run_on_main_thread(_do)

    def import_blend(self, filepath: str, object_names=None, name_prefix: str = None):
        """Hinglish: .blend file se specific object(s) (ya sab, agar
        object_names na diya jaaye) current scene mein APPEND karta hai
        aur unhe scene collection mein link karta hai (append akele se
        sirf bpy.data mein aata hai, scene mein dikhta nahi jab tak
        explicitly link na kiya jaaye)."""
        import os
        if not os.path.isfile(filepath):
            raise ValueError(f"File not found: {filepath}")
        if not filepath.lower().endswith(".blend"):
            raise ValueError(f"import_blend expects a .blend file, got: {filepath}")

        def _do():
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                available = list(data_from.objects)
                if object_names is None:
                    data_to.objects = available
                else:
                    missing = [n for n in object_names if n not in available]
                    if missing:
                        raise ValueError(
                            f"Object(s) {missing} not found in '{filepath}'. "
                            f"Available: {available}"
                        )
                    data_to.objects = [n for n in object_names if n in available]

            imported = []
            for obj in data_to.objects:
                if obj is None:
                    continue
                bpy.context.scene.collection.objects.link(obj)
                if name_prefix:
                    obj.name = f"{name_prefix}{obj.name}"
                imported.append(obj)
            return imported

        return run_on_main_thread(_do)

    def import_model(self, filepath: str, name: str = None, scale=None):
        """Ek local .obj/.fbx/.glb/.gltf file ko scene mein import karta hai."""
        import os
        ext = os.path.splitext(filepath)[1].lower()
        importer = self._IMPORT_OPS.get(ext)
        if importer is None:
            raise ValueError(
                f"Unsupported file extension '{ext}'. Supported: {', '.join(self._IMPORT_OPS)}"
            )
        if not os.path.isfile(filepath):
            raise ValueError(f"File not found: {filepath}")

        def _do():
            before = set(bpy.data.objects)
            try:
                importer(filepath)
            except AttributeError as exc:
                raise ValueError(
                    f"The importer for '{ext}' is not available in this Blender install "
                    f"(is the matching Import-Export addon enabled?): {exc}"
                ) from exc
            imported = [obj for obj in bpy.data.objects if obj not in before]

            if scale is not None:
                for obj in imported:
                    obj.scale = scale

            if name is not None and len(imported) == 1:
                imported[0].name = name

            return imported

        return run_on_main_thread(_do)

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
    # Retopology
    # ---------------------------------------------------------
    @staticmethod
    def _topology_from_bmesh(bm) -> dict:
        """Face/vertex-level topology numbers from an already-built bmesh."""
        face_count = len(bm.faces)
        tri_count = sum(1 for f in bm.faces if len(f.verts) == 3)
        quad_count = sum(1 for f in bm.faces if len(f.verts) == 4)
        ngon_count = face_count - tri_count - quad_count
        # Pole = interior vertex whose valence is not 4 (3-poles and 5+-poles)
        pole_count = sum(
            1 for v in bm.verts if not v.is_boundary and len(v.link_edges) != 4
        )
        return {
            "vertex_count": len(bm.verts),
            "face_count": face_count,
            "tri_count": tri_count,
            "quad_count": quad_count,
            "ngon_count": ngon_count,
            "quad_ratio": (quad_count / face_count) if face_count else 0.0,
            "pole_count": pole_count,
        }

    def get_topology_stats(self, object_name: str):
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None or obj.type != "MESH":
                return None

            import bmesh
            bm = bmesh.new()
            bm.from_mesh(obj.data)
            stats = self._topology_from_bmesh(bm)
            bm.free()
            return stats

        return run_on_main_thread(_do)

    def retopologize(self, object_name: str, method: str = "QUADRIFLOW",
                     target_faces: int = 2000, voxel_size: float = 0.05,
                     decimate_ratio: float = 0.5, preserve_sharp: bool = True,
                     smooth_normals: bool = True, new_name: str = "",
                     hide_original: bool = True):
        """
        Hinglish: Original object ko kabhi modify nahi karta — uski COPY
        banakar usi par remesh chalata hai, aur naya object return karta
        hai. Isse retopology hamesha reversible rehti hai.

        NOTE: bpy.ops yahan active/selected object par chalte hain, isliye
        copy ko active banate hain. Kuch bhi fail ho to copy delete ho jaati hai.
        """
        def _do():
            src = bpy.data.objects.get(object_name)
            if src is None or src.type != "MESH":
                return None

            import bmesh

            def _stats(mesh):
                bm = bmesh.new()
                bm.from_mesh(mesh)
                s = self._topology_from_bmesh(bm)
                bm.free()
                return s

            before = _stats(src.data)

            copy = src.copy()
            copy.data = src.data.copy()
            copy.name = new_name or f"{object_name}_retopo"
            for collection in src.users_collection:
                collection.objects.link(copy)

            view_layer = bpy.context.view_layer
            for o in view_layer.objects:
                o.select_set(False)
            copy.select_set(True)
            view_layer.objects.active = copy

            def _discard_copy():
                mesh = copy.data
                bpy.data.objects.remove(copy, do_unlink=True)
                if mesh.users == 0:
                    bpy.data.meshes.remove(mesh)

            try:
                if method == "QUADRIFLOW":
                    result = bpy.ops.object.quadriflow_remesh(
                        mode="FACES",
                        target_faces=int(target_faces),
                        use_preserve_sharp=bool(preserve_sharp),
                        use_preserve_boundary=True,
                        smooth_normals=bool(smooth_normals),
                    )
                    if "FINISHED" not in result:
                        raise RuntimeError("Quadriflow remesh was cancelled by Blender")
                elif method == "VOXEL":
                    copy.data.remesh_voxel_size = float(voxel_size)
                    result = bpy.ops.object.voxel_remesh()
                    if "FINISHED" not in result:
                        raise RuntimeError("Voxel remesh was cancelled by Blender")
                elif method == "DECIMATE":
                    mod = copy.modifiers.new(name="Retopo_Decimate", type="DECIMATE")
                    mod.ratio = float(decimate_ratio)
                    result = bpy.ops.object.modifier_apply(modifier=mod.name)
                    if "FINISHED" not in result:
                        raise RuntimeError("Decimate apply was cancelled by Blender")
                else:
                    raise ValueError(f"Unsupported retopology method: {method}")
            except Exception:
                _discard_copy()
                raise

            after = _stats(copy.data)

            if hide_original:
                src.hide_set(True)

            return {
                "new_name": copy.name,  # Blender may add .001 suffix on collision
                "method": method,
                "before": before,
                "after": after,
            }

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