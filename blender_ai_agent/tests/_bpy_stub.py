"""
_bpy_stub
=========
Hinglish: Blender ke bahar (plain terminal/CI mein) tests chalane ke liye,
real `bpy` module available nahi hota. Ye file ek minimal fake `bpy`
banake `sys.modules` mein daal deti hai, taaki root __init__.py aur
ui/panel.py ke imports fail na hon.

IMPORTANT: Ye sirf IMPORTS ko satisfy karta hai. Isse koi real Blender
operation nahi hota — bas class definitions load ho jaati hain.

Har test file ke sabse upar isko import karo (side-effect ke liye),
baaki sab imports ke PEHLE.
"""

import sys
import types


def install_fake_bpy():
    if "bpy" in sys.modules:
        return  # already installed, dobara mat karo

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


# Module import hote hi turant install ho jaye
install_fake_bpy()