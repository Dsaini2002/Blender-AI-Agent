"""
fakes.py
========
Hinglish: SceneInspector ko test karne ke liye ek "Fake" BlenderBridge.
Real Blender objects ki jagah plain Python objects use karte hain.
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