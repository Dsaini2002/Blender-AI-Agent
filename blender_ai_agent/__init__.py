"""
Blender AI Agent — Phase 1: Blender Foundation (V1)
=====================================================
No LLM, no Agent, no Vision — sirf deterministic scene understanding.
"""

bl_info = {
    "name": "Blender AI Agent",
    "author": "You",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > AI Agent",
    "description": "Phase 1 deterministic foundation for the Blender AI Agent project.",
    "category": "Object",
}

import bpy

from .bridge.blender_bridge import BlenderBridge
from .inspectors.scene_inspector import SceneInspector
from .tools.registry import ToolRegistry
from .tools.scene_tools import SceneInspectTool
from .ui.panel import AIAgentPanel, AIAGENT_OT_inspect_scene

_bridge: BlenderBridge = None
_registry: ToolRegistry = None


def get_bridge() -> BlenderBridge:
    global _bridge
    if _bridge is None:
        _bridge = BlenderBridge()
    return _bridge


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def _register_tools() -> None:
    registry = get_registry()
    bridge = get_bridge()

    # Dependency chain yahan explicitly assemble hoti hai — ise
    # "Composition Root" kehte hain: poore app mein sirf ek jagah
    # jahan sab dependencies jodi jaati hain.
    inspector = SceneInspector(bridge)
    registry.register(SceneInspectTool(inspector))


classes = (
    AIAGENT_OT_inspect_scene,
    AIAgentPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _register_tools()
    print("[Blender AI Agent] Phase 1 addon registered. Tools:", get_registry().list_tools())


def unregister():
    global _bridge, _registry
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _bridge = None
    _registry = None


if __name__ == "__main__":
    register()