"""
fakes.py
========
Hinglish: SceneInspector, Object/Material/Modifier/Camera/GeometryNodes/
Animation Tools ko test karne ke liye "Fake" BlenderBridge.
"""


class FakeModifier:
    """bpy Modifier jaisa dikhne waala fake modifier."""

    def __init__(self, name, type_):
        self.name = name
        self.type = type_
        self.width = None
        self.levels = None
        self.thickness = None
        self.node_group = None


class FakeModifierCollection:
    """obj.modifiers jaisa dikhne waala fake collection."""

    def __init__(self):
        self._modifiers = []

    def new(self, name, type):
        modifier = FakeModifier(name=name, type_=type)
        self._modifiers.append(modifier)
        return modifier

    def get(self, name):
        for mod in self._modifiers:
            if mod.name == name:
                return mod
        return None

    def remove(self, modifier):
        self._modifiers.remove(modifier)


class FakeObject:
    """bpy Object jaisa dikhne waala fake object."""

    def __init__(self, name, type_="MESH", location=None, rotation=None, scale=None):
        self.name = name
        self.type = type_
        self.location = location or [0.0, 0.0, 0.0]
        self.rotation_euler = rotation or [0.0, 0.0, 0.0]
        self.scale = scale or [1.0, 1.0, 1.0]
        self.material_name = None
        self.modifiers = FakeModifierCollection()
        self.keyframes = []  # list of (frame, location) tuples — Step 9.13


class FakeMaterial:
    """bpy Material jaisa dikhne waala fake material."""

    def __init__(self, name, color=None, roughness=0.5, metallic=0.0):
        self.name = name
        self.color = color or [0.8, 0.8, 0.8, 1.0]
        self.roughness = roughness
        self.metallic = metallic


class FakeBridge:
    """BlenderBridge jaisa interface, lekin bpy ke bina."""

    def __init__(self, scene_name="TestScene", objects=None, materials=None):
        self._scene_name = scene_name
        self._objects = objects or []
        self._materials = materials or []
        self._active_camera = None
        self._last_render_path = None

    # ---------------------------------------------------------
    # Scene / objects
    # ---------------------------------------------------------
    def get_scene_name(self):
        return self._scene_name

    def get_objects(self):
        return self._objects

    def get_object(self, name):
        for obj in self._objects:
            if obj.name == name:
                return obj
        return None

    def create_object(self, name, object_type="MESH", primitive="CUBE", location=None):
        obj = FakeObject(name=name, type_=object_type, location=location or [0.0, 0.0, 0.0])
        self._objects.append(obj)
        return obj

    def delete_object(self, name):
        obj = self.get_object(name)
        if obj is None:
            return False
        self._objects.remove(obj)
        return True

    def duplicate_object(self, name, new_name=None):
        obj = self.get_object(name)
        if obj is None:
            return None

        final_name = new_name or f"{obj.name}.001"
        new_obj = FakeObject(
            name=final_name,
            type_=obj.type,
            location=list(obj.location),
            rotation=list(obj.rotation_euler),
            scale=list(obj.scale),
        )
        self._objects.append(new_obj)
        return new_obj

    def rename_object(self, old_name, new_name):
        obj = self.get_object(old_name)
        if obj is None:
            return None
        obj.name = new_name
        return obj

    def transform_object(self, name, location=None, rotation=None, scale=None):
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
    # Materials — Step 2.5
    # ---------------------------------------------------------
    def get_material(self, name):
        for mat in self._materials:
            if mat.name == name:
                return mat
        return None

    def create_material(self, name, color=None):
        material = FakeMaterial(name=name, color=(list(color) + [1.0]) if color and len(color) == 3 else color)
        self._materials.append(material)
        return material

    def assign_material(self, object_name, material_name):
        obj = self.get_object(object_name)
        material = self.get_material(material_name)

        if obj is None or material is None:
            return False

        obj.material_name = material.name
        return True

    def modify_material(self, name, color=None, roughness=None, metallic=None):
        material = self.get_material(name)
        if material is None:
            return None

        if color is not None:
            material.color = (list(color) + [1.0]) if len(color) == 3 else list(color)
        if roughness is not None:
            material.roughness = roughness
        if metallic is not None:
            material.metallic = metallic

        return material

    # ---------------------------------------------------------
    # Modifiers — Step 2.6
    # ---------------------------------------------------------
    def add_modifier(self, object_name, modifier_name, modifier_type="BEVEL"):
        obj = self.get_object(object_name)
        if obj is None:
            return None
        return obj.modifiers.new(name=modifier_name, type=modifier_type)

    def remove_modifier(self, object_name, modifier_name):
        obj = self.get_object(object_name)
        if obj is None:
            return False

        modifier = obj.modifiers.get(modifier_name)
        if modifier is None:
            return False

        obj.modifiers.remove(modifier)
        return True

    def configure_modifier(self, object_name, modifier_name, properties):
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
    # Camera / Render — Step 2.7
    # ---------------------------------------------------------
    def create_camera(self, name, location=None, rotation=None):
        camera_obj = FakeObject(
            name=name,
            type_="CAMERA",
            location=location or [0.0, 0.0, 0.0],
            rotation=rotation or [0.0, 0.0, 0.0],
        )
        self._objects.append(camera_obj)
        return camera_obj

    def set_active_camera(self, name):
        obj = self.get_object(name)
        if obj is None or obj.type != "CAMERA":
            return False
        self._active_camera = obj
        return True

    def render_preview(self, filepath):
        # Real file save nahi karte tests mein — bas path record karte hain
        self._last_render_path = filepath
        return filepath

    # ---------------------------------------------------------
    # Geometry Nodes — Step 9.8
    # ---------------------------------------------------------
    def add_geometry_nodes(self, object_name, node_group_name):
        obj = self.get_object(object_name)
        if obj is None:
            return None
        return obj.modifiers.new(name=node_group_name, type="NODES")

    def get_geometry_nodes(self, object_name, modifier_name):
        obj = self.get_object(object_name)
        if obj is None:
            return None
        return obj.modifiers.get(modifier_name)

    # ---------------------------------------------------------
    # Animation — Step 9.13
    # ---------------------------------------------------------
    def insert_keyframe(self, object_name, frame, location=None):
        obj = self.get_object(object_name)
        if obj is None:
            return False

        if location is not None:
            obj.location = location

        obj.keyframes.append((frame, list(obj.location)))
        return True

    def get_keyframes(self, object_name):
        obj = self.get_object(object_name)
        if obj is None:
            return []
        return sorted(frame for frame, _ in obj.keyframes)