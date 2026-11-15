"""BlenderBridge"""

import bpy

from .main_thread_dispatch import run_on_main_thread


class BlenderBridge:

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

    def bake_scale(self, name: str) -> bool:
        """Move an object's scale into its mesh (and its children's parent inverse) so the
        object reads scale 1.0 without changing size or position. Imported FBX / glTF files
        often arrive at 0.01, and a model that later "fixes" that to 1.0 makes them 100x bigger."""
        def _do():
            from mathutils import Matrix

            obj = bpy.data.objects.get(name)
            if obj is None:
                return False
            s = [float(v) for v in obj.scale]
            if all(abs(v - 1.0) < 1e-6 for v in s) or any(v <= 1e-9 for v in s):
                return False                       # already 1, or mirrored / degenerate: leave alone
            S = Matrix.Diagonal((s[0], s[1], s[2], 1.0))
            if obj.type == "MESH" and obj.data is not None:
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                obj.data.transform(S)
                obj.data.update()
            elif obj.type == "EMPTY":
                obj.empty_display_size *= max(s)
            else:
                return False
            for child in obj.children:
                child.matrix_parent_inverse = S @ child.matrix_parent_inverse
            obj.scale = (1.0, 1.0, 1.0)
            return True

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Material level —
    # ---------------------------------------------------------
    def get_material(self, name: str):
        return run_on_main_thread(lambda: bpy.data.materials.get(name))

    def create_material(self, name: str, color=None):
        def _do():
            material = bpy.data.materials.new(name=name)
            if getattr(material, "node_tree", None) is None:
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
        if getattr(material, "node_tree", None) is None:
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
        def _do():
            scene = bpy.context.scene
            world = scene.world
            if world is None:
                world = bpy.data.worlds.new("World")
                scene.world = world

            if getattr(world, "node_tree", None) is None:
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
    # Text, collections, saving
    # ---------------------------------------------------------
    def create_text(self, name: str, body: str, location=None, rotation=None, size: float = 1.0,
                    extrude: float = 0.0, align: str = "CENTER"):
        def _do():
            curve = bpy.data.curves.new(name=name, type='FONT')
            curve.body = body
            curve.size = float(size)
            curve.extrude = float(extrude)
            align_x = str(align or "CENTER").upper()
            curve.align_x = align_x if align_x in ("LEFT", "CENTER", "RIGHT", "JUSTIFY", "FLUSH") else "CENTER"
            curve.align_y = 'CENTER'
            obj = bpy.data.objects.new(name=name, object_data=curve)
            bpy.context.collection.objects.link(obj)
            if location is not None:
                obj.location = location
            if rotation is not None:
                obj.rotation_euler = rotation
            return obj

        return run_on_main_thread(_do)

    def move_to_collection(self, names, collection: str, parent: str = "") -> dict:
        """Put objects in `collection` (created under the scene, or under `parent`) and nowhere else."""
        def _do():
            scene = bpy.context.scene
            target = bpy.data.collections.get(collection)
            if target is None:
                target = bpy.data.collections.new(collection)
                holder = bpy.data.collections.get(parent) if parent else None
                (holder or scene.collection).children.link(target)
            elif target.name not in [c.name for c in scene.collection.children_recursive]:
                scene.collection.children.link(target)
            moved, missing = [], []
            for name in names:
                obj = bpy.data.objects.get(name)
                if obj is None:
                    missing.append(name)
                    continue
                if obj.name not in target.objects:
                    target.objects.link(obj)
                for other in list(obj.users_collection):
                    if other != target:
                        other.objects.unlink(obj)
                moved.append(obj.name)
            return {"collection": target.name, "moved": moved, "missing": missing}

        return run_on_main_thread(_do)

    def list_collections(self) -> dict:
        def _do():
            return {c.name: [o.name for o in c.objects] for c in bpy.data.collections}

        return run_on_main_thread(_do)

    def save_blend(self, filepath: str) -> dict:
        def _do():
            bpy.ops.wm.save_as_mainfile(filepath=filepath, check_existing=False)
            return {"filepath": bpy.data.filepath}

        return run_on_main_thread(_do)

    def set_custom_prop(self, name: str, key: str, value) -> bool:
        def _do():
            obj = bpy.data.objects.get(name)
            if obj is None:
                return False
            obj[key] = value
            return True

        return run_on_main_thread(_do)

    def get_custom_prop(self, name: str, key: str):
        def _do():
            obj = bpy.data.objects.get(name)
            return obj.get(key) if obj is not None else None

        return run_on_main_thread(_do)

    def recolor_object(self, name: str, color, keep_texture: bool = True, others=()) -> dict:
        """Change an object's colour. A material used by objects outside `others` is copied first, so only these
        objects change. Textured (node) materials keep their pattern: the colour is mixed in before the shader."""
        def _do():
            obj = bpy.data.objects.get(name)
            if obj is None:
                raise ValueError(f"object '{name}' not found")
            rgba = list(color)[:3] + [1.0]
            data = getattr(obj, "data", None)
            if data is None or not hasattr(data, "materials"):
                raise ValueError(f"'{name}' ({obj.type}) cannot have a material")
            if len(obj.material_slots) == 0:
                mat = bpy.data.materials.new(f"{name}_color")
                mat.use_nodes = True
                data.materials.append(mat)
            allowed = set(others) | {name}
            changed = []
            for slot in obj.material_slots:
                mat = slot.material
                if mat is None:
                    mat = bpy.data.materials.new(f"{name}_color")
                    mat.use_nodes = True
                    slot.material = mat
                users = [o.name for o in bpy.data.objects if any(s.material == mat for s in o.material_slots)]
                if any(u not in allowed for u in users):
                    mat = mat.copy()                         # only the asked objects change colour
                    mat.name = f"{name}_{slot.material.name}"[:60]
                    slot.material = mat
                mat.diffuse_color = rgba
                tree = mat.node_tree if mat.use_nodes else None
                bsdf = next((n for n in tree.nodes if n.type == 'BSDF_PRINCIPLED'), None) if tree else None
                emit = next((n for n in tree.nodes if n.type == 'EMISSION'), None) if tree else None
                target = None
                if bsdf is not None:
                    target = bsdf.inputs.get("Base Color")
                elif emit is not None:
                    target = emit.inputs.get("Color")
                if target is not None:
                    tint = tree.nodes.get("aiagent_tint")
                    if tint is not None:                     # recoloured before: just change the colour
                        b = next(i for i in tint.inputs if i.name == "B" and i.type == 'RGBA')
                        b.default_value = rgba
                    elif target.is_linked and keep_texture:
                        source = target.links[0].from_socket
                        tint = tree.nodes.new("ShaderNodeMix")
                        tint.name = tint.label = "aiagent_tint"
                        tint.data_type = 'RGBA'
                        tint.blend_type = 'MIX'
                        tint.location = (target.node.location.x - 220, target.node.location.y - 200)
                        tint.inputs[0].default_value = 0.8
                        a = next(i for i in tint.inputs if i.name == "A" and i.type == 'RGBA')
                        b = next(i for i in tint.inputs if i.name == "B" and i.type == 'RGBA')
                        out = next(o for o in tint.outputs if o.type == 'RGBA')
                        tree.links.new(source, a)
                        b.default_value = rgba
                        tree.links.new(out, target)
                    else:
                        for link in list(target.links):
                            tree.links.remove(link)
                        target.default_value = rgba
                changed.append(mat.name)
            return {"name": name, "materials": changed}

        return run_on_main_thread(_do)

    def current_blend_path(self) -> str:
        return run_on_main_thread(lambda: bpy.data.filepath or "")

    # ---------------------------------------------------------
    # Custom mesh (vertices + faces)
    # ---------------------------------------------------------
    def create_mesh(self, name: str, vertices, faces, location=None, rotation=None, scale=None,
                    shade_smooth: bool = False):
        def _do():
            mesh = bpy.data.meshes.new(name)
            mesh.from_pydata([tuple(v) for v in vertices], [], [tuple(f) for f in faces])
            mesh.update()
            mesh.validate()
            if shade_smooth:
                for polygon in mesh.polygons:
                    polygon.use_smooth = True

            obj = bpy.data.objects.new(name=name, object_data=mesh)
            bpy.context.collection.objects.link(obj)

            if location is not None:
                obj.location = location
            if rotation is not None:
                obj.rotation_euler = rotation
            if scale is not None:
                obj.scale = scale
            return obj

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Mesh damage (broken / chipped / dented / rough)
    # ---------------------------------------------------------
    def damage_mesh(self, object_name: str, region: str = "top", portion: float = 0.25, strength: float = 0.15,
                    style: str = "broken", seed: int = 1, detail: int = 1):
        def _do():
            import bmesh
            from mathutils import Vector

            from ..tools.mesh_damage import plan_damage, region_vertex_indices

            root = bpy.data.objects.get(object_name)
            if root is None:
                return None
            targets = [root] if root.type == "MESH" else [c for c in root.children_recursive if c.type == "MESH"]
            if not targets:
                return None

            bpy.context.view_layer.update()          # matrix_world taaza ho

            parts = []                               # (obj, bm, inverse_matrix, vertex_offset, face_offset)
            world, faces = [], []
            try:
                for obj in targets:
                    if obj.data.users > 1:
                        obj.data = obj.data.copy()
                    matrix = obj.matrix_world.copy()
                    bm = bmesh.new()
                    bm.from_mesh(obj.data)

                    if detail > 0 and len(targets) == 1:
                        try:
                            bm.verts.ensure_lookup_table()
                            local = [tuple(matrix @ v.co) for v in bm.verts]
                            in_region = region_vertex_indices(local, region, portion)
                            edges = [e for e in bm.edges
                                     if e.verts[0].index in in_region and e.verts[1].index in in_region]
                            if edges:
                                bmesh.ops.subdivide_edges(bm, edges=edges, cuts=int(detail), use_grid_fill=True)
                        except Exception:  # noqa: BLE001 
                            pass

                    bm.verts.ensure_lookup_table()
                    bm.faces.ensure_lookup_table()
                    vertex_offset, face_offset = len(world), len(faces)
                    world.extend(tuple(matrix @ v.co) for v in bm.verts)
                    faces.extend([vertex_offset + v.index for v in f.verts] for f in bm.faces)
                    parts.append((obj, bm, matrix.inverted(), vertex_offset, face_offset))

                plan = plan_damage(world, faces, region, portion, strength, style, seed)

                removed_total = 0
                for obj, bm, inverse, vertex_offset, face_offset in parts:
                    vertex_count, face_count = len(bm.verts), len(bm.faces)
                    for global_index, position in plan.moves.items():
                        if vertex_offset <= global_index < vertex_offset + vertex_count:
                            bm.verts[global_index - vertex_offset].co = inverse @ Vector(position)
                    doomed = [bm.faces[g - face_offset] for g in plan.remove_faces
                              if face_offset <= g < face_offset + face_count]
                    if doomed:
                        bmesh.ops.delete(bm, geom=doomed, context="FACES")
                        removed_total += len(doomed)
                    bm.normal_update()
                    bm.to_mesh(obj.data)
                    obj.data.update()
            finally:
                for _, bm, _, _, _ in parts:
                    bm.free()

            return {
                "object": root.name,
                "meshes": [o.name for o in targets],
                "affected_vertices": plan.affected,
                "moved_vertices": len(plan.moves),
                "removed_faces": removed_total,
            }

        return run_on_main_thread(_do)

    def snapshot_mesh(self, object_name: str):
        def _do():
            root = bpy.data.objects.get(object_name)
            if root is None:
                return None
            targets = [root] if root.type == "MESH" else [c for c in root.children_recursive if c.type == "MESH"]
            if not targets:
                return None
            bpy.context.view_layer.update()
            parts = []
            for obj in targets:
                matrix = obj.matrix_world.copy()
                mesh = obj.data
                parts.append({
                    "name": obj.name,
                    "vertices": [tuple(matrix @ v.co) for v in mesh.vertices],
                    "faces": [list(p.vertices) for p in mesh.polygons],
                })
            return {"root": root.name, "parts": parts}

        return run_on_main_thread(_do)

    def apply_mesh_edit(self, results):
        def _do():
            import bmesh
            from mathutils import Vector

            summary = {"meshes": [], "strategy": [], "uv_preserved": True, "removed_faces": 0,
                       "vertex_count": 0, "face_count": 0}
            for item in results:
                obj = bpy.data.objects.get(item["name"])
                if obj is None or obj.type != "MESH":
                    continue
                if obj.data.users > 1:
                    obj.data = obj.data.copy()
                mesh = obj.data
                inverse = obj.matrix_world.inverted()

                if not item["topology_changed"]:
                    removed = item["removed_faces"]
                    if removed:
                        bm = bmesh.new()
                        bm.from_mesh(mesh)
                        bm.verts.ensure_lookup_table()
                        bm.faces.ensure_lookup_table()
                        for index, position in enumerate(item["vertices"]):
                            bm.verts[index].co = inverse @ Vector(position)
                        bmesh.ops.delete(bm, geom=[bm.faces[i] for i in removed], context="FACES")
                        bm.normal_update()
                        bm.to_mesh(mesh)
                        bm.free()
                        summary["removed_faces"] += len(removed)
                        strategy = "moved vertices + removed faces (UVs kept)"
                    else:
                        for index, position in enumerate(item["vertices"]):
                            mesh.vertices[index].co = inverse @ Vector(position)
                        strategy = "moved vertices (UVs kept)"
                    mesh.update()
                else:
                    old_materials = [p.material_index for p in mesh.polygons]
                    old_smooth = [p.use_smooth for p in mesh.polygons]
                    local = [tuple(inverse @ Vector(p)) for p in item["vertices"]]
                    mesh.clear_geometry()
                    mesh.from_pydata(local, [], [list(f) for f in item["faces"]])
                    mesh.update()
                    for polygon, source in zip(mesh.polygons, item["face_source"]):
                        if old_materials:
                            polygon.material_index = old_materials[source] if 0 <= source < len(old_materials) else old_materials[0]
                        polygon.use_smooth = bool(old_smooth[source]) if 0 <= source < len(old_smooth) else False
                    summary["uv_preserved"] = False
                    strategy = "rebuilt mesh (materials kept, UVs reset)"

                summary["meshes"].append(obj.name)
                summary["strategy"].append(strategy)
                summary["vertex_count"] += len(mesh.vertices)
                summary["face_count"] += len(mesh.polygons)
            return summary

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Node-based (procedural) material
    # ---------------------------------------------------------
    def build_node_material(self, name: str, spec, replace: bool = True):
        from ..tools.shader_nodes import layout, viewport_color

        positions = layout(spec)

        def _socket(node, ref, outputs: bool, node_id: str):
            sockets = node.outputs if outputs else node.inputs
            if str(ref).isdigit():
                index = int(ref)
                if index >= len(sockets):
                    raise ValueError(f"{node_id}: {'output' if outputs else 'input'} number {index} does not exist ({len(sockets)} sockets)")
                return sockets[index]
            for socket in sockets:
                if socket.name == ref and not getattr(socket, "unavailable", False):
                    return socket
            for socket in sockets:
                if socket.name == ref:
                    return socket
            from ..tools.shader_nodes import resolve_socket_name
            live = [s for s in sockets if not getattr(s, "unavailable", False)]
            renamed = resolve_socket_name(str(ref), [s.name for s in live])
            if renamed:
                return next(s for s in live if s.name == renamed)
            names = [s.name for s in sockets if not getattr(s, "unavailable", False)]
            raise ValueError(f"{node_id}: no {'output' if outputs else 'input'} socket '{ref}'. Available: {names}")

        def _set_default(socket, value, where: str):
            current = getattr(socket, "default_value", None)
            try:
                if isinstance(value, list):
                    if hasattr(current, "__len__"):
                        size = len(current)
                        value = (value + [1.0] * size)[:size] if len(value) < size else value[:size]
                    else:
                        value = value[0]
                elif hasattr(current, "__len__") and not isinstance(value, str):
                    value = [float(value)] * len(current) if len(current) != 4 else [float(value)] * 3 + [1.0]
                socket.default_value = value
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"{where}: cannot set value {value!r}: {exc}") from exc

        def _do():
            material = bpy.data.materials.get(name) if replace else None
            if material is None:
                material = bpy.data.materials.new(name=name)
            if getattr(material, "node_tree", None) is None:
                material.use_nodes = True
            tree = material.node_tree
            tree.nodes.clear()
            built = {}
            for node_spec in spec.nodes:
                try:
                    node = tree.nodes.new(node_spec.idname)
                except Exception as exc:  # noqa: BLE001
                    raise ValueError(f"{node_spec.id}: this Blender has no node '{node_spec.idname}' ({exc})") from exc
                node.name = node_spec.id
                node.label = node_spec.id
                node.location = positions[node_spec.id]
                built[node_spec.id] = node
                for key, value in node_spec.props.items():
                    try:
                        setattr(node, key, value)
                    except Exception as exc:  # noqa: BLE001
                        raise ValueError(f"{node_spec.id}: cannot set {key}={value!r}: {exc}") from exc
                for key, value in node_spec.inputs.items():
                    _set_default(_socket(node, key, False, node_spec.id), value, f"{node_spec.id}.{key}")
                if node_spec.ramp:
                    elements = node.color_ramp.elements
                    while len(elements) < len(node_spec.ramp):
                        elements.new(0.5)
                    while len(elements) > len(node_spec.ramp):
                        elements.remove(elements[len(elements) - 1])
                    for element, (position, colour) in zip(elements, node_spec.ramp):
                        element.position = position
                        element.color = colour
                if node_spec.image:
                    image = bpy.data.images.load(node_spec.image, check_existing=True)
                    image.colorspace_settings.name = node_spec.colorspace or "sRGB"
                    node.image = image
            for from_id, from_socket, to_id, to_socket in spec.links:
                tree.links.new(_socket(built[from_id], from_socket, True, from_id), _socket(built[to_id], to_socket, False, to_id))
            notes = []
            tint = viewport_color(spec)
            if tint is not None:
                try:
                    material.diffuse_color = tint
                except Exception:  # noqa: BLE001
                    pass
            for key, value in spec.settings.items():
                try:
                    if key == "surface_render_method" and not hasattr(material, "surface_render_method"):
                        material.blend_method = "BLEND" if value == "BLENDED" else "HASHED"      # purane Blender
                    else:
                        setattr(material, key, value)
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"setting {key} skipped: {exc}")
            return {"name": material.name, "nodes": len(spec.nodes), "links": len(spec.links), "notes": notes}

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Render / colour management / DOF / world
    # ---------------------------------------------------------
    def setup_render(self, **opts):
        """engine (eevee|cycles), view_transform, look, exposure, samples, denoise, resolution_x/y, film_transparent,"""
        def _enum_items(owner, prop):
            try:
                return [item.identifier for item in owner.bl_rna.properties[prop].enum_items]
            except Exception:  # noqa: BLE001
                return []

        def _try_set(owner, prop, candidates):
            """Dynamic enums (view_transform, look) do not list their items through bl_rna in every Blender
            version, so just try each candidate value."""
            for value in candidates:
                try:
                    setattr(owner, prop, value)
                    return value
                except (TypeError, ValueError, AttributeError):
                    continue
            return None

        def _do():
            scene = bpy.context.scene
            changed, notes = {}, []
            engine = opts.get("engine")
            if engine:
                wanted = {"eevee": ["BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"], "cycles": ["CYCLES"]}.get(str(engine).lower(), [str(engine).upper()])
                items = _enum_items(scene.render, "engine")
                # Cycles registers itself at runtime, so bl_rna may not list it: try every candidate.
                pick = _try_set(scene.render, "engine", [w for w in wanted if w in items] + wanted)
                if pick:
                    changed["engine"] = pick
                else:
                    notes.append(f"engine '{engine}' not available (have {items})")
            view = opts.get("view_transform")
            if view:
                items = _enum_items(scene.view_settings, "view_transform")
                # bl_rna can list placeholder identifiers (e.g. 'NONE') that the real enum rejects,
                # so every candidate is tried, matched items first.
                matched = [i for i in items if i.lower() == str(view).lower()]
                pick = _try_set(scene.view_settings, "view_transform",
                                matched + [str(view), str(view).title(), str(view).upper()])
                if pick:
                    changed["view_transform"] = pick
                else:
                    notes.append(f"view transform '{view}' not available (have {items})")
            look = opts.get("look")
            if look:
                items = _enum_items(scene.view_settings, "look")
                base = scene.view_settings.view_transform
                candidates = [str(look), f"{base} - {look}", f"AgX - {look}", f"Filmic - {look}"]
                if str(look).strip().lower() == "none":
                    candidates = ["None", f"{base} - None", "NONE"]
                matched = [i for c in candidates for i in items if i.lower() == c.lower()]
                pick = _try_set(scene.view_settings, "look", list(dict.fromkeys(matched + candidates)))
                if pick:
                    changed["look"] = pick
                else:
                    notes.append(f"look '{look}' not available (have {items[:8]})")
            if opts.get("exposure") is not None:
                scene.view_settings.exposure = float(opts["exposure"])
                changed["exposure"] = float(opts["exposure"])
            if opts.get("resolution_x") and opts.get("resolution_y"):
                scene.render.resolution_x, scene.render.resolution_y = int(opts["resolution_x"]), int(opts["resolution_y"])
                scene.render.resolution_percentage = 100
                changed["resolution"] = [int(opts["resolution_x"]), int(opts["resolution_y"])]
            if opts.get("samples"):
                try:
                    if scene.render.engine == "CYCLES":
                        scene.cycles.samples = int(opts["samples"])
                    else:
                        scene.eevee.taa_render_samples = int(opts["samples"])
                    changed["samples"] = int(opts["samples"])
                except Exception as exc:  # noqa: BLE001
                    notes.append(f"samples skipped: {exc}")
            if opts.get("denoise") is not None and scene.render.engine == "CYCLES":
                scene.cycles.use_denoising = bool(opts["denoise"])
                changed["denoise"] = bool(opts["denoise"])
            if opts.get("film_transparent") is not None:
                scene.render.film_transparent = bool(opts["film_transparent"])
                changed["film_transparent"] = bool(opts["film_transparent"])
            if opts.get("dof") is not None:
                camera = scene.camera
                if camera is None or camera.type != "CAMERA":
                    notes.append("depth of field skipped: the scene has no camera (create one with camera.create first)")
                else:
                    camera.data.dof.use_dof = bool(opts["dof"])
                    if opts.get("aperture"):
                        camera.data.dof.aperture_fstop = float(opts["aperture"])
                    focus = opts.get("focus_object")
                    if focus:
                        target = bpy.data.objects.get(focus)
                        if target is None:
                            notes.append(f"focus object '{focus}' not found")
                        else:
                            camera.data.dof.focus_object = target
                    changed["dof"] = bool(opts["dof"])
            if opts.get("world_color") is not None or opts.get("world_strength") is not None:
                world = scene.world or bpy.data.worlds.new("World")
                scene.world = world
                if getattr(world, "node_tree", None) is None:
                    world.use_nodes = True
                background = world.node_tree.nodes.get("Background")
                if background is None:
                    notes.append("world has no Background node; world colour skipped")
                else:
                    if opts.get("world_color") is not None:
                        color = list(opts["world_color"])[:3] + [1.0]
                        background.inputs["Color"].default_value = color
                        changed["world_color"] = color[:3]
                    if opts.get("world_strength") is not None:
                        background.inputs["Strength"].default_value = float(opts["world_strength"])
                        changed["world_strength"] = float(opts["world_strength"])
            return {"changed": changed, "notes": notes}

        return run_on_main_thread(_do)

    def scene_snapshot(self) -> dict:
        """READ-ONLY picture of the whole scene for the error finder: every object with its world box, transform,
        materials, collections, light / camera data and how much of it the active camera sees. Changes nothing."""
        def _do():
            from mathutils import Vector
            try:
                from bpy_extras.object_utils import world_to_camera_view
            except Exception:  # noqa: BLE001
                world_to_camera_view = None

            scene = bpy.context.scene
            bpy.context.view_layer.update()
            camera = scene.camera
            objects = []
            for obj in scene.objects:
                entry = {"name": obj.name, "type": obj.type,
                         "location": [round(v, 4) for v in obj.location],
                         "rotation": [round(v, 4) for v in obj.rotation_euler],
                         "scale": [round(v, 4) for v in obj.scale],
                         "dimensions": [round(v, 4) for v in obj.dimensions],
                         "parent": obj.parent.name if obj.parent else "",
                         "collections": [c.name for c in obj.users_collection],
                         "hidden": bool(obj.hide_viewport or obj.hide_render or obj.hide_get()),
                         "materials": [], "box": None, "in_view": None}
                data = getattr(obj, "data", None)
                if data is not None and hasattr(data, "materials"):
                    entry["materials"] = [m.name if m else "" for m in data.materials]
                if obj.type == "MESH":
                    entry["vertices"] = len(data.vertices)
                    entry["faces"] = len(data.polygons)
                if obj.type in ("MESH", "CURVE", "SURFACE", "META", "FONT"):
                    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
                    entry["box"] = {"min": [round(min(c[k] for c in corners), 4) for k in range(3)],
                                    "max": [round(max(c[k] for c in corners), 4) for k in range(3)]}
                    if camera is not None and world_to_camera_view is not None:
                        seen = 0
                        for c in corners:
                            p = world_to_camera_view(scene, camera, c)
                            if 0.0 <= p.x <= 1.0 and 0.0 <= p.y <= 1.0 and p.z > 0:
                                seen += 1
                        entry["in_view"] = round(seen / 8.0, 3)
                if obj.type == "LIGHT":
                    entry["light"] = {"type": data.type, "energy": round(float(data.energy), 3),
                                      "color": [round(v, 3) for v in data.color]}
                if obj.type == "CAMERA":
                    entry["camera"] = {"lens": round(float(data.lens), 2), "active": obj == camera}
                objects.append(entry)
            world = scene.world
            return {"objects": objects, "camera": camera.name if camera else "",
                    "engine": scene.render.engine,
                    "collections": {c.name: len(c.objects) for c in bpy.data.collections},
                    "world": world.name if world else "", "frame": scene.frame_current}

        return run_on_main_thread(_do)

    def measure_objects(self, names):
        def _do():
            from mathutils import Vector

            bpy.context.view_layer.update()
            lo, hi, found = [1e18] * 3, [-1e18] * 3, False
            for name in names:
                root = bpy.data.objects.get(name)
                if root is None:
                    continue
                for obj in [root] + list(root.children_recursive):
                    if obj.type not in ("MESH", "CURVE", "SURFACE", "META", "FONT"):
                        continue
                    for corner in obj.bound_box:
                        world = obj.matrix_world @ Vector(corner)
                        for k in range(3):
                            lo[k], hi[k] = min(lo[k], world[k]), max(hi[k], world[k])
                        found = True
            return {"min": lo, "max": hi} if found else None

        return run_on_main_thread(_do)

    def render_views(self, names, views, resolution: int = 512, out_dir: str = None, stem: str = "view", focus=None):
        """Render `names` from each view. focus = a few of them: the camera frames only those (a zoom-in close-up)
        while the rest stays visible around them."""
        import math
        import os
        import tempfile

        from ..tools.render_views import camera_pose, normalize_view

        out_dir = out_dir or tempfile.gettempdir()
        os.makedirs(out_dir, exist_ok=True)
        view_names = [normalize_view(v) for v in views]

        def _do(view_names, cutaways):
            from mathutils import Vector

            scene = bpy.context.scene
            render = scene.render
            bpy.context.view_layer.update()

            keep = set()
            for name in names:
                root = bpy.data.objects.get(name)
                if root is not None:
                    keep.add(root.name)
                    keep.update(child.name for child in root.children_recursive)
            lo, hi, found = [1e18] * 3, [-1e18] * 3, False
            for name in keep:
                obj = bpy.data.objects.get(name)
                if obj is None or obj.type not in ("MESH", "CURVE", "SURFACE", "META", "FONT"):
                    continue
                for corner in obj.bound_box:
                    world = obj.matrix_world @ Vector(corner)
                    for k in range(3):
                        lo[k], hi[k] = min(lo[k], world[k]), max(hi[k], world[k])
                    found = True
            if not found:
                raise ValueError("nothing to render: the given objects have no geometry")

            saved = (scene.camera, render.filepath, render.resolution_x, render.resolution_y, render.resolution_percentage,
                     render.image_settings.file_format)
            hidden = [o for o in scene.objects if o.name not in keep and not o.hide_render]
            cam_data = bpy.data.cameras.new("_aiagent_tmp_cam")
            cam = bpy.data.objects.new("_aiagent_tmp_cam", cam_data)
            sun_data = bpy.data.lights.new("_aiagent_tmp_sun", "SUN")
            sun = bpy.data.objects.new("_aiagent_tmp_sun", sun_data)
            paths = []
            try:
                scene.collection.objects.link(cam)
                scene.collection.objects.link(sun)
                cam_data.lens, cam_data.sensor_width = 50.0, 36.0
                sun_data.energy = 3.5
                sun.rotation_euler = (math.radians(50), 0.0, math.radians(35))
                for obj in hidden:
                    obj.hide_render = True
                render.resolution_x = render.resolution_y = int(resolution)
                render.resolution_percentage = 100
                render.image_settings.file_format = "PNG"
                scene.camera = cam
                quick = self._fast_render_begin(scene)
                from ..tools.render_views import occluders
                boxes = {}
                for name in keep:
                    obj = bpy.data.objects.get(name)
                    if obj is None or obj.type not in ("MESH", "CURVE", "SURFACE", "META", "FONT"):
                        continue
                    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
                    boxes[name] = {"min": [min(p[k] for p in pts) for k in range(3)],
                                   "max": [max(p[k] for p in pts) for k in range(3)]}
                from ..tools.render_views import framing_box
                focus_boxes = [boxes[n] for n in (focus or []) if n in boxes]
                if focus_boxes:
                    frame_lo = [min(b["min"][k] for b in focus_boxes) for k in range(3)]
                    frame_hi = [max(b["max"][k] for b in focus_boxes) for k in range(3)]
                else:
                    frame_lo, frame_hi = framing_box(boxes, lo, hi)
                for view in view_names:
                    from ..copilot import activity
                    if activity.should_stop():
                        raise RuntimeError("Stopped by user.")       # no more renders after Stop
                    pose = camera_pose(frame_lo, frame_hi, view)
                    cam.location = pose["location"]
                    direction = Vector(pose["target"]) - Vector(pose["location"])
                    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
                    # see INTO enclosed scenes: hide the roof and the walls on the camera's side for this view
                    blockers = [bpy.data.objects.get(n) for n in occluders(boxes, lo, hi, pose["location"])]
                    blockers = [o for o in blockers if o is not None and not o.hide_render]
                    for obj in blockers:
                        obj.hide_render = True
                    try:
                        path = os.path.join(out_dir, f"{stem}_{view}.png")
                        render.filepath = path
                        bpy.ops.render.render(write_still=True)
                        paths.append(path)
                    finally:
                        for obj in blockers:
                            obj.hide_render = False
                # buildings made by mesh.building: one more close view with the outer walls hidden, so the
                # reviewer sees the rooms, halls and furniture instead of reporting them as missing
                from ..tools.render_views import building_cutaways, cutaway_pose
                for prefix, envelope in (sorted(building_cutaways(keep).items())[:2] if cutaways and not focus else []):
                    box = boxes.get(prefix + "_walls")
                    if box is None:
                        continue
                    pose = cutaway_pose(box["min"], box["max"])
                    cam.location = pose["location"]
                    direction = Vector(pose["target"]) - Vector(pose["location"])
                    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
                    blockers = [bpy.data.objects.get(n) for n in envelope]
                    blockers = [o for o in blockers if o is not None and not o.hide_render]
                    for obj in blockers:
                        obj.hide_render = True
                    try:
                        path = os.path.join(out_dir, f"{stem}_cutaway_{prefix}.png")
                        render.filepath = path
                        bpy.ops.render.render(write_still=True)
                        paths.append(path)
                    finally:
                        for obj in blockers:
                            obj.hide_render = False
            finally:
                if "quick" in locals():
                    self._fast_render_end(scene, quick)
                for obj in hidden:
                    obj.hide_render = False
                (scene.camera, render.filepath, render.resolution_x, render.resolution_y, render.resolution_percentage,
                 render.image_settings.file_format) = saved
                bpy.data.objects.remove(cam, do_unlink=True)
                bpy.data.objects.remove(sun, do_unlink=True)
                bpy.data.cameras.remove(cam_data)
                bpy.data.lights.remove(sun_data)
            missing = [p for p in paths if not os.path.isfile(p)]
            if missing:
                raise RuntimeError(f"render finished but no image was written: {missing[0]}")
            return paths

        # one image per main-thread call: Blender's UI stays alive between images, so the Stop button can be
        # pressed (and is honoured) in the middle of a deep check - not only after all of its renders
        from ..copilot import activity
        paths = []
        for index, view in enumerate(view_names):
            if activity.should_stop():
                raise RuntimeError("Stopped by user.")
            last = index == len(view_names) - 1
            paths += run_on_main_thread(lambda v=view, c=last: _do([v], c))
        if not view_names:
            paths += run_on_main_thread(lambda: _do([], True))
        return paths

    # ---------------------------------------------------------
    # Curves
    # ---------------------------------------------------------
    def create_curve(self, name: str, points, curve_type: str = "BEZIER", thickness: float = 0.05,
                     closed: bool = False, location=None, rotation=None, scale=None,
                     fill_caps: bool = True, resolution: int = 12, strokes=None):
        def _do():
            curve_data = bpy.data.curves.new(name=name, type="CURVE")
            curve_data.dimensions = "3D"
            curve_data.resolution_u = int(resolution)
            curve_data.bevel_depth = float(thickness)
            curve_data.bevel_resolution = 4
            curve_data.use_fill_caps = bool(fill_caps)

            for stroke in (strokes or [points]):
                self._add_spline(curve_data, stroke, curve_type, closed)

            obj = bpy.data.objects.new(name=name, object_data=curve_data)
            bpy.context.collection.objects.link(obj)

            if location is not None:
                obj.location = location
            if rotation is not None:
                obj.rotation_euler = rotation
            if scale is not None:
                obj.scale = scale

            return obj

        return run_on_main_thread(_do)

    @staticmethod
    def _add_spline(curve_data, points, curve_type, closed):
        spline = curve_data.splines.new(curve_type)
        count = len(points)

        if curve_type == "BEZIER":
            spline.bezier_points.add(count - 1)
            for bezier_point, point in zip(spline.bezier_points, points):
                bezier_point.co = (point[0], point[1], point[2])
                bezier_point.radius = point[3] if len(point) > 3 else 1.0
                bezier_point.handle_left_type = "AUTO"
                bezier_point.handle_right_type = "AUTO"
        else:
            spline.points.add(count - 1)
            for spline_point, point in zip(spline.points, points):
                spline_point.co = (point[0], point[1], point[2], 1.0)
                spline_point.radius = point[3] if len(point) > 3 else 1.0
            if curve_type == "NURBS":
                spline.order_u = min(4, count)
                spline.use_endpoint_u = True

        spline.use_cyclic_u = bool(closed)

    # ---------------------------------------------------------
    # Modifier level —
    # ---------------------------------------------------------
    def add_modifier(self, object_name: str, modifier_name: str, modifier_type: str = "BEVEL"):
        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return None
            return obj.modifiers.new(name=modifier_name, type=modifier_type)

        return run_on_main_thread(_do)

    def set_object_visibility(self, object_name: str, hide: bool) -> bool:
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

    _IMPORT_OPS = {
        ".obj": lambda filepath: bpy.ops.wm.obj_import(filepath=filepath),
        ".fbx": lambda filepath: bpy.ops.import_scene.fbx(filepath=filepath),
        ".glb": lambda filepath: bpy.ops.import_scene.gltf(filepath=filepath),
        ".gltf": lambda filepath: bpy.ops.import_scene.gltf(filepath=filepath),
    }

    def list_blend_objects(self, filepath: str):
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

        def _do():
            camera_obj = bpy.data.objects.get(name)
            if camera_obj is None or camera_obj.type != "CAMERA":
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

        def _do():
            obj = bpy.data.objects.get(name)
            if obj is None or obj.type != 'CAMERA':
                return False

            bpy.context.scene.camera = obj
            return True

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Checkpoints for "Revert AI changes"
    # ---------------------------------------------------------
    def save_checkpoint(self, filepath: str) -> dict:
        """Write every object of the scene (with its mesh, materials, modifiers) to a small .blend, so a later
        restore brings back deleted objects and edited meshes too - not only transforms."""
        def _do():
            scene = bpy.context.scene
            objects = list(scene.objects)
            info = {"objects": [{"name": o.name, "collections": [c.name for c in o.users_collection]} for o in objects],
                    "camera": scene.camera.name if scene.camera else None,
                    "scene_collection": scene.collection.name}
            bpy.data.libraries.write(filepath, set(objects), fake_user=False)
            return info

        return run_on_main_thread(_do)

    def restore_checkpoint(self, filepath: str, info: dict) -> dict:
        def _do():
            scene = bpy.context.scene
            removed = [o.name for o in scene.objects]
            old_data, old_materials = [], []
            for obj in list(scene.objects):
                if obj.data is not None:
                    old_data.append(obj.data)
                    old_materials.extend(m for m in getattr(obj.data, "materials", []) or [] if m is not None)
                bpy.data.objects.remove(obj, do_unlink=True)
            # free the old meshes / materials first, so the restored ones keep their names (no '.001' copies)
            for block in old_data + old_materials:
                try:
                    if block.users == 0:
                        for pool in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights,
                                     bpy.data.materials):
                            if block.name in pool and pool[block.name] == block:
                                pool.remove(block)
                                break
                except ReferenceError:
                    pass                                    # already gone (shared by two removed objects)
            wanted = [entry["name"] for entry in info.get("objects", [])]
            with bpy.data.libraries.load(filepath, link=False) as (data_from, data_to):
                data_to.objects = [name for name in data_from.objects if name in wanted]
            restored = []
            by_name = {entry["name"]: entry for entry in info.get("objects", [])}
            for obj in data_to.objects:
                if obj is None:
                    continue
                entry = by_name.get(obj.name, {})
                linked = False
                for col_name in entry.get("collections", []):
                    collection = scene.collection if col_name == info.get("scene_collection") \
                        else bpy.data.collections.get(col_name)
                    if collection is not None and obj.name not in collection.objects:
                        collection.objects.link(obj)
                        linked = True
                if not linked:
                    scene.collection.objects.link(obj)
                restored.append(obj.name)
            camera = info.get("camera")
            if camera and bpy.data.objects.get(camera) is not None:
                scene.camera = bpy.data.objects[camera]
            return {"removed": len(removed), "restored": restored}

        return run_on_main_thread(_do)

    @staticmethod
    def _fast_render_begin(scene, samples: int = 16):
        """Switch to a quick EEVEE render (Cycles at 128 samples froze Blender for 40+ s per image).
        Returns what to restore."""
        saved = {"engine": scene.render.engine}
        for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                scene.render.engine = engine
                break
            except (TypeError, ValueError, AttributeError):
                continue
        eevee = getattr(scene, "eevee", None)
        if eevee is not None and hasattr(eevee, "taa_render_samples"):
            saved["eevee_samples"] = eevee.taa_render_samples
            eevee.taa_render_samples = int(samples)
        return saved

    @staticmethod
    def _fast_render_end(scene, saved) -> None:
        try:
            scene.render.engine = saved["engine"]
        except (TypeError, ValueError, AttributeError, KeyError):
            pass
        eevee = getattr(scene, "eevee", None)
        if eevee is not None and "eevee_samples" in saved:
            eevee.taa_render_samples = saved["eevee_samples"]

    def render_preview(self, filepath: str, resolution=None, fast: bool = False) -> str:
        import os
        import tempfile

        from ..image_paths import image_format_for, resolve_image_path

        filepath = resolve_image_path(filepath, "preview.png")
        directory = os.path.dirname(filepath)
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            pass
        if not os.path.isdir(directory) or not os.access(directory, os.W_OK):
            filepath = os.path.join(tempfile.gettempdir(), os.path.basename(filepath))

        def _do():
            scene = bpy.context.scene
            render = scene.render
            saved = (render.filepath, render.resolution_x, render.resolution_y,
                     render.resolution_percentage, render.image_settings.file_format)
            quick = self._fast_render_begin(scene) if fast else None
            try:
                render.filepath = filepath
                render.image_settings.file_format = image_format_for(filepath)
                size = resolution if resolution is not None else ((960, 540) if fast else None)
                if size is not None:
                    render.resolution_x, render.resolution_y = int(size[0]), int(size[1])
                    render.resolution_percentage = 100
                bpy.ops.render.render(write_still=True)
            finally:
                (render.filepath, render.resolution_x, render.resolution_y,
                 render.resolution_percentage, render.image_settings.file_format) = saved
                if quick is not None:
                    self._fast_render_end(scene, quick)

            if not os.path.isfile(filepath):
                raise RuntimeError(f"Render finished but no image was written at {filepath}")
            return filepath

        return run_on_main_thread(_do)

    # ---------------------------------------------------------
    # Geometry Nodes —
    # ---------------------------------------------------------
    def add_geometry_nodes(self, object_name: str, node_group_name: str):

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

        def _do():
            obj = bpy.data.objects.get(object_name)
            if obj is None:
                return None
            return obj.modifiers.get(modifier_name)

        return run_on_main_thread(_do)
    # ---------------------------------------------------------
    # Geometry QA —
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
    # Animation —
    # ---------------------------------------------------------
    def insert_keyframe(self, object_name: str, frame: int, location=None):

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