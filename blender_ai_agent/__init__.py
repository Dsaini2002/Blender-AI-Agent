"""
Blender AI Agent — Phase 1 + Phase 2 (Step 2.7)
==================================================
"""

bl_info = {
    "name": "Blender AI Agent",
    "author": "You",
    "version": (0, 5, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > AI Agent",
    "description": "Deterministic tool system for the Blender AI Agent project.",
    "category": "Object",
}

import bpy

from .bridge.blender_bridge import BlenderBridge
from .inspectors.scene_inspector import SceneInspector
from .tools.registry import ToolRegistry
from .tools.scene_tools import SceneInspectTool
from .tools.object_tools import (
    CreateObjectTool,
    DeleteObjectTool,
    DuplicateObjectTool,
    RenameObjectTool,
    TransformObjectTool,
)
from .tools.material_tools import (
    CreateMaterialTool,
    AssignMaterialTool,
    ModifyMaterialTool,
)
from .tools.modifier_tools import (
    AddModifierTool,
    RemoveModifierTool,
    ConfigureModifierTool,
)
from .tools.camera_tools import (
    CreateCameraTool,
    SetCameraTool,
    RenderPreviewTool,
)
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
    """Composition Root — saare tools yahin assemble hote hain."""
    registry = get_registry()
    bridge = get_bridge()

    # Scene tools
    inspector = SceneInspector(bridge)
    registry.register(SceneInspectTool(inspector))

    # Object tools — Step 2.4
    registry.register(CreateObjectTool(bridge))
    registry.register(DeleteObjectTool(bridge))
    registry.register(DuplicateObjectTool(bridge))
    registry.register(RenameObjectTool(bridge))
    registry.register(TransformObjectTool(bridge))

    # Material tools — Step 2.5
    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))
    registry.register(ModifyMaterialTool(bridge))

    # Modifier tools — Step 2.6
    registry.register(AddModifierTool(bridge))
    registry.register(RemoveModifierTool(bridge))
    registry.register(ConfigureModifierTool(bridge))

    # Camera / Render tools — Step 2.7
    registry.register(CreateCameraTool(bridge))
    registry.register(SetCameraTool(bridge))
    registry.register(RenderPreviewTool(bridge))


classes = (
    AIAGENT_OT_inspect_scene,
    AIAgentPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    _register_tools()
    print("[Blender AI Agent] Registered. Tools:", get_registry().list_tools())


def unregister():
    global _bridge, _registry
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    _bridge = None
    _registry = None


if __name__ == "__main__":
    register()