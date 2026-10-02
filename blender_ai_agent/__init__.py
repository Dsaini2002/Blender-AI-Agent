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
from .tools.asset_tools import ImportBlendTool, ImportModelTool, ListBlendObjectsTool
from .tools.python_power_tool import PythonPowerTool
from .tools.retopology_tools import AnalyzeTopologyTool, RetopologyTool
from .tools.lighting_tools import CreateLightTool, SetWorldTool
from .tools.template_tools import BuildTemplateTool
from .vision.tool import VisionObserveTool
from .ui.panel import (
    AIAgentPanel,
    AIAGENT_OT_inspect_scene,
    AIAGENT_OT_copilot_submit,
    AIAGENT_OT_switch_provider,
    AIAGENT_OT_run_inspection,
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

    registry.register(ImportModelTool(bridge))
    registry.register(ListBlendObjectsTool(bridge))
    registry.register(ImportBlendTool(bridge))
    registry.register(BuildTemplateTool(bridge))

    # Retopology: analyze (READ_ONLY) + remesh (SAFE_WRITE, always makes a copy)
    registry.register(AnalyzeTopologyTool(bridge))
    registry.register(RetopologyTool(bridge))

    # Scene mood: lights + world background
    registry.register(CreateLightTool(bridge))
    registry.register(SetWorldTool(bridge))

    # Hinglish: PYTHON_EXECUTION - sirf ye zaroori hai jab structured
    # tools (object.create/transform/modifier) us geometry ko achieve
    # nahi kar sakte (bmesh edit-mode ops, loop cuts, custom extrusions).
    # Permission.PYTHON_EXECUTION hamesha confirmation maangta hai
    # (see autonomy/modes.py AutonomyPolicy) - kabhi silently auto-run
    # nahi hota.
    registry.register(PythonPowerTool(bridge))

    # Hinglish: vision.observe - render ko khud "dekh" kar issues
    # (floating parts, overlaps, missing bevels) detect karne ke liye.
    # Real provider chahiye - agar GEMINI_API_KEY set hai to Gemini
    # Vision use karta hai, warna is tool ko register hi nahi karte
    # (bina real provider ke sirf crash karega).
    import os
    if os.environ.get("GEMINI_API_KEY", ""):
        from .vision.analyzer import VisionAnalyzer
        from .vision.capture import RenderCapture
        from .vision.providers.gemini_vision_provider import GeminiVisionProvider

        vision_analyzer = VisionAnalyzer(
            capture=RenderCapture(bridge),
            vision_provider=GeminiVisionProvider(api_key=os.environ["GEMINI_API_KEY"]),
        )
        registry.register(VisionObserveTool(vision_analyzer))


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


_tool_caller: object = None
_skill_registry = None


def get_tool_caller():
    """
    Hinglish: Pehle har get_copilot_controller() call apna naya
    ToolCaller banata tha (harmless tha, kyunki ye sirf ToolRegistry
    ko wrap karta hai). Ab isse singleton banaya hai taaki Skills
    (jo apne constructor mein ek ToolCaller chahti hain — dependency
    injection pattern) hamesha WAHI, live ToolCaller use karein jo
    Agent bhi use kar raha hai.
    """
    global _tool_caller
    if _tool_caller is None:
        from .agent.tool_caller import ToolCaller
        _ensure_tools_registered()
        _tool_caller = ToolCaller(get_registry())
    return _tool_caller


def get_skill_registry():
    """
    Hinglish: Tools ki tarah hi — saare built-in Skills (jaise
    HouseBuilderSkill) yahan register hote hain. CopilotController
    isse "fast path" ke liye use karta hai (Step: Skill fast-path) —
    agar user ka message kisi Skill se confidently match karta hai
    (e.g. "house"), to LLM call kiye bina hi directly execute hoti hai.
    """
    global _skill_registry
    if _skill_registry is None:
        from .skills.registry import SkillRegistry
        from .skills.builtins.house_builder import HouseBuilderSkill
        from .skills.builtins.product_showcase import ProductShowcaseSkill
        from .skills.builtins.campsite import CampsiteSkill

        tool_caller = get_tool_caller()

        registry = SkillRegistry()
        registry.register(HouseBuilderSkill(tool_caller))
        registry.register(ProductShowcaseSkill(tool_caller))
        registry.register(CampsiteSkill(tool_caller))
        _skill_registry = registry

    return _skill_registry


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

        groq_key = os.environ.get("GROQ_API_KEY", "")
        if groq_key:
            from .providers.groq_provider import GroqProvider
            registry.register(
                "groq",
                lambda **kwargs: GroqProvider(api_key=groq_key, model_name=kwargs.get("model_name", "openai/gpt-oss-120b")),
            )

        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            from .providers.openai_provider import OpenAIProvider
            registry.register(
                "openai",
                lambda **kwargs: OpenAIProvider(api_key=openai_key, model_name=kwargs.get("model_name", "gpt-6-astra")),
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
        from .copilot.controller import CopilotController
        from .observability.logger import Logger
        from .reliability.recovery import RecoveryManager

        _ensure_tools_registered()
        bridge = get_bridge()
        registry = get_registry()
        provider_registry = get_provider_registry()

        tool_caller = get_tool_caller()
        skill_registry = get_skill_registry()
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
            max_failed_steps=3,
            # Hinglish: 25 kaafi tha jab tasks chhote the. Ab template.build
            # (25-33 parts), vision improve-loop (2-3 rounds, har round mein
            # kai turns), aur room/interior jaisi badi scenes normal ho gayi
            # hain — 25 baar-baar hit ho raha tha. 60 zyada realistic hai.
            max_iterations=60,
        )

        existing_session = _copilot_controller.session if _copilot_controller else None
        _copilot_controller = CopilotController(
            agent, session=existing_session,
            skill_registry=skill_registry, tool_caller=tool_caller,
        )
        _copilot_controller.current_provider_name = chosen_name

    return _copilot_controller


classes = (
    AIAGENT_OT_inspect_scene,
    AIAGENT_OT_copilot_submit,
    AIAGENT_OT_switch_provider,
    AIAGENT_OT_run_inspection,
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
            ('groq', "Groq (Free, fast)", "Groq's free-tier hosted models (requires GROQ_API_KEY)"),
            ('openai', "OpenAI (GPT-6 Astra)", "OpenAI's flagship model, e.g. GPT-6 Astra (requires your own OPENAI_API_KEY, paid)"),
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
            ('gemini-3.5-flash-lite', "Gemini 3.5 Flash Lite", "Lightweight, cheaper"),
        ],
        default='gemini-3.6-flash',
    )
    bpy.types.Scene.aiagent_groq_model_choice = bpy.props.EnumProperty(
        name="Groq Model",
        description="Choose which Groq-hosted model to use",
        items=[
            ('openai/gpt-oss-120b', "GPT-OSS 120B", "Higher-reasoning free model"),
            ('openai/gpt-oss-20b', "GPT-OSS 20B", "Faster, lighter free model"),
            ('qwen/qwen3.6-27b', "Qwen3 32B", "Alternative free model"),
        ],
        default='openai/gpt-oss-120b',
    )
    bpy.types.Scene.aiagent_openai_model_choice = bpy.props.EnumProperty(
        name="OpenAI Model",
        description="Choose which OpenAI-hosted model to use",
        items=[
            ('gpt-6-astra', "GPT-6 Astra", "OpenAI's flagship model"),
            ('gpt-6-astra-pro', "GPT-6 Astra Pro", "Astra with pro reasoning, slower/pricier"),
        ],
        default='gpt-6-astra',
    )
    bpy.types.Scene.aiagent_copilot_input = bpy.props.StringProperty(
        name="Copilot Input",
        description="Type your request for the AI Copilot",
    )
    bpy.types.Scene.aiagent_is_running = bpy.props.BoolProperty(
        name="Copilot Running",
        default=False,
    )
    bpy.types.Scene.aiagent_status_text = bpy.props.StringProperty(
        name="Copilot Status",
        default="",
    )
    bpy.types.Scene.aiagent_qa_report_text = bpy.props.StringProperty(
        name="QA Report",
        default="",
    )
    bpy.types.Scene.aiagent_qa_passed = bpy.props.BoolProperty(
        name="QA Passed",
        default=False,
    )
    bpy.types.Scene.aiagent_qa_retries = bpy.props.IntProperty(
        name="QA Retries",
        default=0,
    )
    bpy.types.Scene.aiagent_qa_report_text = bpy.props.StringProperty(
        name="QA Report",
        default="",
    )
    _ensure_tools_registered()
    print("[Blender AI Agent] Registered. Tools:", get_registry().list_tools())


def unregister():
    global _bridge, _registry, _copilot_controller, _tools_registered
    global _tool_caller, _skill_registry, _provider_registry
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.aiagent_provider_choice
    del bpy.types.Scene.aiagent_model_choice
    del bpy.types.Scene.aiagent_groq_model_choice
    del bpy.types.Scene.aiagent_openai_model_choice
    del bpy.types.Scene.aiagent_copilot_input
    del bpy.types.Scene.aiagent_is_running
    del bpy.types.Scene.aiagent_status_text
    del bpy.types.Scene.aiagent_qa_report_text
    del bpy.types.Scene.aiagent_qa_passed
    del bpy.types.Scene.aiagent_qa_retries
    _bridge = None
    _registry = None
    _copilot_controller = None
    _tools_registered = False
    _tool_caller = None
    _skill_registry = None
    _provider_registry = None

if __name__ == "__main__":
    register()