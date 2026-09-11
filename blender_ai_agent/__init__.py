"""
Blender AI Agent — Phase 1 through Phase 6
==============================================
"""

bl_info = {
    "name": "Blender AI Agent",
    "author": "You",
    "version": (0, 6, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > AI Agent",
    "description": "Deterministic tool system + reliable, vision-aware AI Copilot for Blender.",
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
from .ui.panel import AIAgentPanel, AIAGENT_OT_inspect_scene, AIAGENT_OT_copilot_submit

_bridge: BlenderBridge = None
_registry: ToolRegistry = None
_copilot_controller = None


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


def get_copilot_controller():
    """
    Hinglish: CopilotController ka single, shared instance —
    Agent (RepairableExecutionLoop) ke saath already wired.
    Lazy imports isliye taaki root __init__.py load hote waqt
    agent/reliability/observability/copilot packages sirf tab
    import hon jab copilot actually use ho — circular import se bhi bachate hain.
    """
    global _copilot_controller
    if _copilot_controller is None:
        from .agent.repair_loop import RepairableExecutionLoop
        from .agent.context import ContextManager
        from .agent.planner import Planner
        from .agent.tool_caller import ToolCaller
        from .copilot.controller import CopilotController
        from .observability.logger import Logger
        from .providers.mock_provider import MockProvider
        from .reliability.recovery import RecoveryManager

        bridge = get_bridge()
        registry = get_registry()

        tool_caller = ToolCaller(registry)
        context_manager = ContextManager(registry.get("scene.inspect"))
        planner = Planner()
        recovery = RecoveryManager(tool_caller)
        logger = Logger()

        # Hinglish: Abhi MockProvider — real OpenAI/Anthropic provider
        # baad mein yahan sirf ek line badal ke plug hoga (Open/Closed
        # Principle — baaki kuch chhedna nahi padega).
        provider = MockProvider(responses=[])

        agent = RepairableExecutionLoop(
            model_provider=provider,
            tool_caller=tool_caller,
            context_manager=context_manager,
            planner=planner,
            bridge=bridge,
            recovery_manager=recovery,
            logger=logger,
        )

        _copilot_controller = CopilotController(agent)

    return _copilot_controller


classes = (
    AIAGENT_OT_inspect_scene,
    AIAGENT_OT_copilot_submit,
    AIAgentPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.aiagent_copilot_input = bpy.props.StringProperty(
        name="Copilot Input",
        description="Type your request for the AI Copilot",
    )
    _register_tools()
    print("[Blender AI Agent] Registered. Tools:", get_registry().list_tools())


def unregister():
    global _bridge, _registry, _copilot_controller
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.aiagent_copilot_input
    _bridge = None
    _registry = None
    _copilot_controller = None


if __name__ == "__main__":
    register()