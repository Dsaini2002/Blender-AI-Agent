"""_bpy_stub"""

import sys
import types


def install_fake_bpy():
    if "bpy" in sys.modules:
        return

    fake_bpy = types.ModuleType("bpy")

    # ---- bpy.types ----
    fake_types = types.ModuleType("bpy.types")
    fake_types.Operator = type("Operator", (), {})
    fake_types.Panel = type("Panel", (), {})

    # ---- bpy.utils ----
    fake_utils = types.ModuleType("bpy.utils")
    fake_utils.register_class = lambda cls: None
    fake_utils.unregister_class = lambda cls: None

    # ---- bpy.context / bpy.data / bpy.ops ----
    fake_bpy.types = fake_types
    fake_bpy.utils = fake_utils
    fake_bpy.context = types.SimpleNamespace(scene=None, active_object=None)
    fake_bpy.data = types.SimpleNamespace(objects=[])
    fake_bpy.ops = types.SimpleNamespace()

    sys.modules["bpy"] = fake_bpy
    sys.modules["bpy.types"] = fake_types
    sys.modules["bpy.utils"] = fake_utils


install_fake_bpy()