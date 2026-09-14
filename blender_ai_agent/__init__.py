"""
Blender AI Agent — Phase 1 through Phase 11
================================================
"""

bl_info = {
    "name": "Blender AI Agent",
    "author": "You",
    "version": (0, 11, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > AI Agent",
    "description": "Deterministic tool system + reliable, vision-aware, autonomous AI Copilot for Blender.",
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
from .ui.panel import (
    AIAgentPanel,
    AIAGENT_OT_inspect_scene,
    AIAGENT_OT_copilot_submit,
    AIAGENT_OT_switch_provider,
)

_bridge: BlenderBridge = None
_registry: ToolRegistry = None
_copilot_controller = None
_provider_registry = None
_tools_registered = False


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

    inspector = SceneInspector(bridge)
    registry.register(SceneInspectTool(inspector))

    registry.register(CreateObjectTool(bridge))
    registry.register(DeleteObjectTool(bridge))
    registry.register(DuplicateObjectTool(bridge))
    registry.register(RenameObjectTool(bridge))
    registry.register(TransformObjectTool(bridge))

    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))
    registry.register(ModifyMaterialTool(bridge))

    registry.register(AddModifierTool(bridge))
    registry.register(RemoveModifierTool(bridge))
    registry.register(ConfigureModifierTool(bridge))

    registry.register(CreateCameraTool(bridge))
    registry.register(SetCameraTool(bridge))
    registry.register(RenderPreviewTool(bridge))


def _ensure_tools_registered() -> None:
    """
    Hinglish: Safety net — agar kisi wajah se (reload, new file, etc.)
    register() ke through tools register nahi hue, ye lazily register
    kar deta hai jab bhi zaroorat pade.
    """
    global _tools_registered
    if not _tools_registered:
        _register_tools()
        _tools_registered = True


def get_provider_registry():
    """Hinglish: Saare available AI providers yahan register hote hain."""
    global _provider_registry
    if _provider_registry is None:
        import os
        from .providers.registry import ProviderRegistry
        from .providers.mock_provider import MockProvider

        registry = ProviderRegistry()
        registry.register("mock", lambda **kwargs: MockProvider(responses=[]))

        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if gemini_key:
            from .providers.gemini_provider import GeminiProvider
            registry.register(
                "gemini",
                lambda **kwargs: GeminiProvider(api_key=gemini_key, model_name=kwargs.get("model_name", "gemini-3.6-flash")),
            )

        _provider_registry = registry

    return _provider_registry


def get_copilot_controller(provider_name: str = None, model_name: str = None):
    """
    Hinglish: CopilotController ka single, shared instance.
    `provider_name` diya gaya toh us provider ke saath naya banega,
    nahi diya toh existing instance milega ya default banega.
    """
    global _copilot_controller

    if provider_name is not None or _copilot_controller is None:
        from .agent.repair_loop import RepairableExecutionLoop
        from .agent.context import ContextManager
        from .agent.planner import Planner
        from .agent.tool_caller import ToolCaller
        from .copilot.controller import CopilotController
        from .observability.logger import Logger
        from .reliability.recovery import RecoveryManager

        _ensure_tools_registered()
        bridge = get_bridge()
        registry = get_registry()
        provider_registry = get_provider_registry()

        tool_caller = ToolCaller(registry)
        context_manager = ContextManager(registry.get("scene.inspect"))
        planner = Planner()
        recovery = RecoveryManager(tool_caller)
        logger = Logger()

        chosen_name = provider_name or ("gemini" if "gemini" in provider_registry.list_providers() else "mock")
        create_kwargs = {"model_name": model_name} if model_name else {}
        provider = provider_registry.create(chosen_name, **create_kwargs)

        agent = RepairableExecutionLoop(
            model_provider=provider,
            tool_caller=tool_caller,
            context_manager=context_manager,
            planner=planner,
            bridge=bridge,
            recovery_manager=recovery,
            logger=logger,
        )

        existing_session = _copilot_controller.session if _copilot_controller else None
        _copilot_controller = CopilotController(agent, session=existing_session)
        _copilot_controller.current_provider_name = chosen_name

    return _copilot_controller


classes = (
    AIAGENT_OT_inspect_scene,
    AIAGENT_OT_copilot_submit,
    AIAGENT_OT_switch_provider,
    AIAgentPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.aiagent_provider_choice = bpy.props.EnumProperty(
        name="Provider",
        description="Choose which AI provider to use",
        items=[
            ('mock', "Mock (Testing)", "Fake provider for testing, no real AI"),
            ('gemini', "Google Gemini", "Google's Gemini AI (requires GEMINI_API_KEY)"),
        ],
        default='mock',
    )
    bpy.types.Scene.aiagent_model_choice = bpy.props.EnumProperty(
        name="Model",
        description="Choose which Gemini model to use",
        items=[
            ('gemini-3.6-flash', "Gemini 3.6 Flash", "Latest fast model"),
            ('gemini-flash-latest', "Gemini Flash (Latest)", "Always points to newest flash model"),
            ('gemini-3.1-pro-preview', "Gemini 3.1 Pro (Preview)", "Stronger reasoning, preview"),
            ('gemini-2.5-flash-lite', "Gemini 2.5 Flash Lite", "Lightweight, cheaper"),
        ],
        default='gemini-3.6-flash',
    )
    bpy.types.Scene.aiagent_copilot_input = bpy.props.StringProperty(
        name="Copilot Input",
        description="Type your request for the AI Copilot",
    )
    _ensure_tools_registered()
    print("[Blender AI Agent] Registered. Tools:", get_registry().list_tools())


def unregister():
    global _bridge, _registry, _copilot_controller, _tools_registered
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.aiagent_provider_choice
    del bpy.types.Scene.aiagent_model_choice
    del bpy.types.Scene.aiagent_copilot_input
    _bridge = None
    _registry = None
    _copilot_controller = None
    _tools_registered = False

if __name__ == "__main__":
    register()