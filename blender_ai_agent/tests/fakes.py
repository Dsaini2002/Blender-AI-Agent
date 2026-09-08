"""
fakes.py
========
Hinglish: SceneInspector aur Object Tools ko test karne ke liye
"Fake" BlenderBridge. Real Blender objects ki jagah plain Python
objects use karte hain.
"""


class FakeObject:
    """bpy Object jaisa dikhne waala fake object (duck typing)."""

    def __init__(self, name, type_="MESH", location=None, rotation=None, scale=None):
        self.name = name
        self.type = type_
        self.location = location or [0.0, 0.0, 0.0]
        self.rotation_euler = rotation or [0.0, 0.0, 0.0]
        self.scale = scale or [1.0, 1.0, 1.0]


class FakeBridge:
    """BlenderBridge jaisa interface, lekin bpy ke bina."""

    def __init__(self, scene_name="TestScene", objects=None):
        self._scene_name = scene_name
        self._objects = objects or []

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