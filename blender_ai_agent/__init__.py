"""Blender AI Agent"""

bl_info = {
    "name": "Blender AI Agent",
    "author": "Dinesh Saini",
    "version": (0, 16, 5),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar (N) > AI Agent",
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
from .tools.field_markings import FieldMarkingsTool
from .tools.grandstand import MeshGrandstandTool
from .tools.building import MeshBuildingTool
from .tools.edit_tools import MoveByTool, RecolorTool
from .tools.site_tools import MeshBoundaryWallTool, SceneOrganizeTool, SceneSaveTool, TextCreateTool
from .tools.placement_tools import MeasureObjectsTool, MoveOffPathTool, PlaceNextToTool, PlaceOnTool, SnapToGroundTool
from .tools.retopology_tools import AnalyzeTopologyTool, RetopologyTool
from .tools.lighting_tools import CreateLightTool, SetWorldTool
from .tools.curve_tools import CreateCurveTool
from .tools.mesh_tools import CreateMeshTool, DamageMeshTool
from .tools.character_tools import CharacterCreateTool
from .tools.iterate_tools import BuildIterateTool
from .tools.shader_tools import MaterialNodesTool, MaterialRecipeTool, RenderSetupTool
from .tools.mesh_advanced_tools import (
    MeshEditTool, MeshHelpTool, MeshLatheTool, MeshPrismTool, MeshScriptTool, MeshSdfTool, MeshTerrainTool,
)
from .tools.library_tools import LibraryListTool, LibraryPlaceTool
from .tools.local_assets_tools import PlaceLocalAssetTool, SearchLocalAssetsTool
from .tools.template_tools import BuildTemplateTool
from .vision.tool import VisionObserveTool
from .ui.progress_panel import AIAGENT_PT_progress, register_progress_timer, unregister_progress_timer
from .ui.panel import (
    AIAGENT_PromptLine,
    AIAGENT_UL_prompt_lines,
    AIAgentPanel,
    AIAGENT_OT_open_checks,
    AIAGENT_OT_find_errors,
    AIAGENT_OT_copilot_continue,
    AIAGENT_OT_save_key,
    AIAGENT_OT_inspect_scene,
    AIAGENT_OT_copilot_submit,
    AIAGENT_OT_copilot_stop,
    AIAGENT_OT_approve,
    AIAGENT_OT_memory_forget,
    AIAGENT_OT_switch_provider,
    AIAGENT_OT_run_inspection,
    AIAGENT_OT_prompt_paste,
    AIAGENT_OT_prompt_copy,
    AIAGENT_OT_prompt_clear,
    AIAGENT_OT_reply_copy,
    AIAGENT_OT_reply_clear,
    AIAGENT_OT_use_recent,
    AIAGENT_OT_retry,
    AIAGENT_OT_view_log,
    AIAGENT_OT_revert,
    AIAGENT_OT_quick_prompt,
    AIAGENT_OT_open_prefs,
    on_prompt_changed,
    on_provider_changed,
)
from .prefs import AIAgentPreferences, apply_keys

_bridge: BlenderBridge = None
_registry: ToolRegistry = None
_copilot_controller = None
_provider_registry = None
_post_verifier = None
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
    registry = get_registry()
    bridge = get_bridge()

    inspector = SceneInspector(bridge)
    registry.register(SceneInspectTool(inspector))

    registry.register(CreateObjectTool(bridge))
    registry.register(DeleteObjectTool(bridge))
    registry.register(DuplicateObjectTool(bridge))
    registry.register(RenameObjectTool(bridge))
    registry.register(TransformObjectTool(bridge))
    registry.register(MeasureObjectsTool(bridge))
    registry.register(PlaceOnTool(bridge))
    registry.register(PlaceNextToTool(bridge))
    registry.register(SnapToGroundTool(bridge))
    registry.register(MoveOffPathTool(bridge))

    registry.register(CreateMaterialTool(bridge))
    registry.register(AssignMaterialTool(bridge))
    registry.register(ModifyMaterialTool(bridge))
    # Pro shading + finishing: node-based materials, tayyar recipes (aag/dhuan/lakdi/patthar/sheesha...), render/colour/DOF setup
    registry.register(MaterialNodesTool(bridge))
    registry.register(MaterialRecipeTool(bridge))
    registry.register(RenderSetupTool(bridge))

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

    # Curves + ready-made model library (campfire, trees, tent...)
    registry.register(CreateCurveTool(bridge))
    registry.register(CreateMeshTool(bridge))   # custom vertices+faces shapes
    registry.register(DamageMeshTool(bridge))   # broken / chipped / dented / rough

    # Advanced mesh toolkit: edit ANY object (preset / operators / formula) + generators (lathe, terrain, sdf, prism)
    registry.register(MeshEditTool(bridge))
    registry.register(MeshScriptTool(bridge))
    registry.register(MeshLatheTool(bridge))
    registry.register(MeshTerrainTool(bridge))
    registry.register(MeshSdfTool(bridge))
    registry.register(MeshPrismTool(bridge))
    registry.register(MeshGrandstandTool(bridge))   # stepped stadium / court seating
    registry.register(FieldMarkingsTool(bridge))    # regulation football / tennis / cricket lines
    registry.register(RecolorTool(bridge))
    registry.register(MoveByTool(bridge))            # move a whole library model by an offset           # change the colour of what is already there
    registry.register(MeshBuildingTool(bridge))     # complete multi-storey building with rooms and halls
    registry.register(MeshBoundaryWallTool(bridge))  # compound wall, gate, security cabin
    registry.register(TextCreateTool(bridge))        # 3D text for sign boards
    registry.register(SceneOrganizeTool(bridge))     # collections the user asked for
    registry.register(SceneSaveTool(bridge))         # save as a named .blend
    registry.register(MeshHelpTool(bridge))
    registry.register(CharacterCreateTool(bridge))   # cartoon character / face
    registry.register(BuildIterateTool(bridge, lambda: get_tool_caller(), lambda: get_registry()))
    registry.register(LibraryListTool(bridge))
    registry.register(LibraryPlaceTool(bridge))
    registry.register(SearchLocalAssetsTool(bridge))
    registry.register(PlaceLocalAssetTool(bridge))

    registry.register(PythonPowerTool(bridge))

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
    global _tools_registered
    if not _tools_registered:
        _register_tools()
        _tools_registered = True


_tool_caller: object = None
_skill_registry = None


def get_tool_caller():
    global _tool_caller
    if _tool_caller is None:
        from .agent.tool_caller import ToolCaller
        _ensure_tools_registered()
        _tool_caller = ToolCaller(get_registry())
    return _tool_caller


def get_post_run_verifier():
    global _post_verifier
    if _post_verifier is None:
        from .agent.post_verify import PostRunVerifier
        _post_verifier = PostRunVerifier(get_tool_caller(), get_bridge())
    return _post_verifier


def get_skill_registry():
    global _skill_registry
    if _skill_registry is None:
        from .skills.registry import SkillRegistry
        from .skills.builtins.house_builder import HouseBuilderSkill
        from .skills.builtins.product_showcase import ProductShowcaseSkill
        from .skills.builtins.campsite import CampsiteSkill
        from .skills.builtins.library_props import LibraryPropSkill
        from .skills.builtins.cartoon_character import CartoonCharacterSkill
        from .skills.builtins.iterative_build import IterativeBuildSkill

        tool_caller = get_tool_caller()

        registry = SkillRegistry()
        registry.register(HouseBuilderSkill(tool_caller))
        registry.register(ProductShowcaseSkill(tool_caller))
        registry.register(CampsiteSkill(tool_caller))
        registry.register(LibraryPropSkill(tool_caller))
        registry.register(CartoonCharacterSkill(tool_caller))
        registry.register(IterativeBuildSkill(tool_caller))
        _skill_registry = registry

    return _skill_registry


def get_provider_registry():
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

        claude_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
        if claude_key:
            from .providers.claude_provider import DEFAULT_MODEL as _CLAUDE_DEFAULT, ClaudeProvider
            registry.register(
                "claude",
                lambda **kwargs: ClaudeProvider(api_key=claude_key, model_name=kwargs.get("model_name", _CLAUDE_DEFAULT)),
            )

        openai_key = os.environ.get("OPENAI_API_KEY", "")
        if openai_key:
            from .providers.openai_provider import OpenAIProvider
            registry.register(
                "openai",
                lambda **kwargs: OpenAIProvider(api_key=openai_key, model_name=kwargs.get("model_name", "gpt-6-sol")),
            )

        _provider_registry = registry

    return _provider_registry


def refresh_provider_registry() -> None:
    """Read the API keys again (a key saved in the preferences / another scene after start-up) - the Copilot
    and its conversation stay."""
    global _provider_registry
    _provider_registry = None


def reset_providers() -> None:
    """A key was added or changed: build the providers and the Copilot again on next use."""
    global _provider_registry, _copilot_controller
    _provider_registry = None
    _copilot_controller = None


_live_memory = None


def get_live_memory():
    """Memory that survives restarts (~/BlenderAIAgent/memory.json)."""
    global _live_memory
    if _live_memory is None:
        from .memory.live import LiveMemory
        _live_memory = LiveMemory.from_file()
    return _live_memory


def _project_id() -> str:
    """Name of the open .blend file (memories about built objects are kept per file)."""
    from .bridge.main_thread_dispatch import run_on_main_thread
    try:
        return run_on_main_thread(lambda: bpy.path.basename(bpy.data.filepath)) or "unsaved"
    except Exception:  # noqa: BLE001
        return "unsaved"


def _maybe_route(provider_registry, provider_name, model_name, strong):
    """Smart routing: trivial edits go to a lighter model of the same provider; everything else uses the chosen model."""
    from .routing.model_router import RoutingProvider, fast_model_for
    try:
        enabled = bool(getattr(bpy.context.scene, "aiagent_smart_routing", True))
    except Exception:  # noqa: BLE001
        enabled = True
    fast_model = fast_model_for(provider_name, model_name or "")
    if not enabled or not fast_model:
        return strong, None
    try:
        fast = provider_registry.create(provider_name, model_name=fast_model)
    except Exception:  # noqa: BLE001
        return strong, None
    return RoutingProvider(fast, strong, fast_name=fast_model, strong_name=model_name or ""), fast_model


def get_copilot_controller(provider_name: str = None, model_name: str = None):
    global _copilot_controller

    if provider_name is not None or _copilot_controller is None:
        if _copilot_controller is not None:
            try:
                _copilot_controller.cancel()     # a run of the replaced Copilot must not go on in the background
            except Exception:  # noqa: BLE001
                pass
        from .agent.repair_loop import RepairableExecutionLoop
        from .agent.context import ContextManager
        from .agent.planner import Planner
        from .copilot.controller import CopilotController
        from .observability.logger import Logger
        from .reliability.recovery import RecoveryManager
        from .autonomy.guardrails import GuardrailLimits

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

        available = provider_registry.list_providers()
        if provider_name is None and _copilot_controller is None:
            try:
                preferred = bpy.context.scene.aiagent_provider_choice
            except Exception:  # noqa: BLE001
                preferred = None
            order = [preferred] + ["gemini", "claude", "openai"]
            provider_name = next((p for p in order if p and p in available), None)
            if provider_name is not None and model_name is None:
                try:
                    from .ui.panel import _selected_model
                    model_name = _selected_model(bpy.context.scene, provider_name)
                except Exception:  # noqa: BLE001
                    model_name = None
        chosen_name = provider_name or "mock"
        import os
        os.environ["BLENDER_AI_ACTIVE_PROVIDER"] = chosen_name        # the automatic check looks with the same AI
        os.environ["BLENDER_AI_ACTIVE_MODEL"] = model_name or ""
        create_kwargs = {"model_name": model_name} if model_name else {}
        provider = provider_registry.create(chosen_name, **create_kwargs)
        provider, fast_model = _maybe_route(provider_registry, chosen_name, model_name, provider)

        agent = RepairableExecutionLoop(
            model_provider=provider,
            tool_caller=tool_caller,
            context_manager=context_manager,
            planner=planner,
            bridge=bridge,
            recovery_manager=recovery,
            logger=logger,
            max_failed_steps=3,
            max_iterations=60,
            guardrails=GuardrailLimits(max_steps=300, max_retries=30, max_runtime_seconds=1200.0,
                                       max_scene_changes=600),
        )

        from .multi_agent.team import TeamPlanner
        team_planner = TeamPlanner(lambda: agent._model_provider,
                                   scene_summary=lambda: context_manager.build_context_text()[:3000])

        existing_session = _copilot_controller.session if _copilot_controller else None
        _copilot_controller = CopilotController(
            agent, session=existing_session,
            skill_registry=skill_registry, tool_caller=tool_caller,
            verifier=get_post_run_verifier(),
            memory=get_live_memory(), project_id_getter=_project_id, team_planner=team_planner,
        )
        _copilot_controller.fast_model_name = fast_model
        _copilot_controller.current_provider_name = chosen_name
        _copilot_controller.current_model_name = model_name if chosen_name != "mock" else None

    return _copilot_controller


classes = (
    AIAGENT_PromptLine,
    AIAGENT_UL_prompt_lines,
    AIAGENT_OT_inspect_scene,
    AIAGENT_OT_copilot_submit,
    AIAGENT_OT_switch_provider,
    AIAGENT_OT_run_inspection,
    AIAGENT_OT_copilot_stop,
    AIAGENT_OT_approve,
    AIAGENT_OT_memory_forget,
    AIAGENT_OT_prompt_paste,
    AIAGENT_OT_prompt_copy,
    AIAGENT_OT_prompt_clear,
    AIAGENT_OT_reply_copy,
    AIAGENT_OT_reply_clear,
    AIAGENT_OT_use_recent,
    AIAGENT_OT_retry,
    AIAGENT_OT_view_log,
    AIAGENT_OT_revert,
    AIAGENT_OT_quick_prompt,
    AIAGENT_OT_open_prefs,
    AIAGENT_OT_save_key,
    AIAGENT_OT_open_checks,
    AIAGENT_OT_find_errors,
    AIAGENT_OT_copilot_continue,
    AIAgentPreferences,
    AIAgentPanel,
)

_addon_keymaps = []


def _register_keymaps():
    try:
        kc = bpy.context.window_manager.keyconfigs.addon
    except Exception:  # noqa: BLE001
        kc = None
    if kc is None:
        return
    km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
    for idname, key in (("aiagent.prompt_paste", 'V'), ("aiagent.reply_copy", 'C'), ("aiagent.copilot_submit", 'RET')):
        kmi = km.keymap_items.new(idname, key, 'PRESS', ctrl=True, alt=True)
        _addon_keymaps.append((km, kmi))


def _unregister_keymaps():
    for km, kmi in _addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:  # noqa: BLE001
            pass
    _addon_keymaps.clear()


def register():
    try:
        from .observability.run_trace import enable_crash_dump
        enable_crash_dump()                      # a hard Blender crash still leaves the Python stacks on disk
    except Exception:  # noqa: BLE001
        pass
    for cls in classes:
        bpy.utils.register_class(cls)
    try:
        apply_keys()                    # keys pasted in the panel / preferences -> environment
    except Exception as exc:  # noqa: BLE001
        print(f"[Blender AI Agent] could not read saved API keys: {exc}")
    register_progress_timer()
    _register_keymaps()
    bpy.types.Scene.aiagent_provider_choice = bpy.props.EnumProperty(
        name="Provider",
        description="Choose which AI provider to use",
        items=[
            ('gemini', "Google Gemini", "Google's Gemini models (requires GEMINI_API_KEY)"),
            ('claude', "Anthropic Claude", "Claude models (requires ANTHROPIC_API_KEY, paid)"),
            ('openai', "OpenAI", "OpenAI models (requires OPENAI_API_KEY, paid)"),
        ],
        default='gemini',
        update=on_provider_changed,
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
        update=on_provider_changed,
    )
    from .providers.claude_provider import DEFAULT_MODEL as _CLAUDE_DEFAULT, MODELS as _CLAUDE_MODELS
    bpy.types.Scene.aiagent_claude_model_choice = bpy.props.EnumProperty(
        name="Claude Model",
        description="Choose which Anthropic Claude model to use",
        items=[(m, label, desc) for m, label, desc in _CLAUDE_MODELS],
        default=_CLAUDE_DEFAULT,
        update=on_provider_changed,
    )
    bpy.types.Scene.aiagent_openai_model_choice = bpy.props.EnumProperty(
        name="OpenAI Model",
        description="Choose which OpenAI-hosted model to use",
        items=[
            ('gpt-6-luna', "GPT-6 Luna (cheapest)", "Light, fast and cheapest ($0.10 / $0.50 per 1M tokens) - "
                                                    "simple scenes and edits"),
            ('gpt-6-sol', "GPT-6 Sol (balanced)", "Strong for building scenes at a fifth of Astra's price "
                                                  "($2 / $10 per 1M tokens)"),
            ('gpt-6-astra', "GPT-6 Astra (strongest)", "OpenAI's flagship - most capable, most expensive "
                                                       "($10 / $50 per 1M tokens)"),
            ('gpt-6-astra-pro', "GPT-6 Astra Pro", "Astra with pro reasoning, slower/pricier"),
        ],
        default='gpt-6-sol',
        update=on_provider_changed,
    )
    bpy.types.Scene.aiagent_copilot_input = bpy.props.StringProperty(
        name="Prompt",
        description="Describe what to create or modify. Ctrl+V pastes every line of a multi-line text",
        default="",
        update=on_prompt_changed,
    )
    bpy.types.Scene.aiagent_prompt_lines = bpy.props.CollectionProperty(type=AIAGENT_PromptLine,
                                                                         options={'SKIP_SAVE'})
    bpy.types.Scene.aiagent_prompt_line_index = bpy.props.IntProperty(default=-1, options={'SKIP_SAVE'})
    bpy.types.Scene.aiagent_key_input = bpy.props.StringProperty(
        name="API key", description="Paste the API key here, then press Submit Key", default="", subtype='PASSWORD',
        options={'SKIP_SAVE'})
    bpy.types.Scene.aiagent_change_key = bpy.props.BoolProperty(
        name="Change key", description="Paste a different API key", default=False, options={'SKIP_SAVE'})
    bpy.types.Scene.aiagent_show_settings = bpy.props.BoolProperty(
        name="Settings", description="Show provider, model and API key settings", default=False)
    bpy.types.Scene.aiagent_scene_context = bpy.props.BoolProperty(
        name="Scene Context",
        description="Send the selected objects with the prompt, so 'make it red' knows what 'it' is",
        default=True)
    bpy.types.Scene.aiagent_show_history = bpy.props.BoolProperty(
        name="Recent Tasks", description="Show recent tasks", default=True)
    bpy.types.Scene.aiagent_team_mode = bpy.props.BoolProperty(
        name="Team",
        description="Big requests: a lead plans steps and layout / modeling / materials / lighting specialists build them",
        default=True,
    )
    bpy.types.Scene.aiagent_smart_routing = bpy.props.BoolProperty(
        name="Smart routing",
        description="Use a lighter, faster model for simple requests and the chosen model for complex ones (saves quota)",
        default=True,
        update=on_provider_changed,
    )
    bpy.types.Scene.aiagent_memory = bpy.props.BoolProperty(
        name="Memory",
        description="Remember your preferences and what was built in this file, across sessions",
        default=True,
    )
    bpy.types.Scene.aiagent_ask_mode = bpy.props.EnumProperty(
        name="Ask before",
        description="When the Copilot must ask you before a step runs",
        items=[
            ('ASSISTED', "Risky steps", "Ask before Python code and before deleting objects you already had"),
            ('MANUAL', "Every change", "Ask before every step that changes the scene"),
            ('AUTONOMOUS', "Python only", "Ask only before running Python code"),
        ],
        default='ASSISTED',
    )
    bpy.types.Scene.aiagent_last_prompt = bpy.props.StringProperty(name="Last Prompt", default="")
    bpy.types.Scene.aiagent_last_reply = bpy.props.StringProperty(name="Last Response", default="")
    bpy.types.Scene.aiagent_last_reply_ok = bpy.props.BoolProperty(name="Last Response OK", default=True)
    bpy.types.Scene.aiagent_is_running = bpy.props.BoolProperty(
        name="Copilot Running",
        default=False,
    )
    bpy.types.Scene.aiagent_last_error = bpy.props.StringProperty(
        name="Last Error",
        default="",
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
    _ensure_tools_registered()
    print("[Blender AI Agent] Registered. Tools:", get_registry().list_tools())


def unregister():
    try:
        from .observability.run_trace import disable_crash_dump, end_file
        end_file()
        disable_crash_dump()
    except Exception:  # noqa: BLE001
        pass
    global _bridge, _registry, _copilot_controller, _tools_registered
    global _tool_caller, _skill_registry, _provider_registry, _post_verifier, _live_memory
    unregister_progress_timer()
    _unregister_keymaps()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.aiagent_provider_choice
    del bpy.types.Scene.aiagent_model_choice
    del bpy.types.Scene.aiagent_openai_model_choice
    for prop in ("aiagent_key_input", "aiagent_change_key"):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)
    del bpy.types.Scene.aiagent_claude_model_choice
    del bpy.types.Scene.aiagent_copilot_input
    for _name in ("aiagent_prompt_lines", "aiagent_prompt_line_index"):
        if hasattr(bpy.types.Scene, _name):
            delattr(bpy.types.Scene, _name)
    for _name in ("aiagent_show_settings", "aiagent_scene_context", "aiagent_show_history"):
        if hasattr(bpy.types.Scene, _name):
            delattr(bpy.types.Scene, _name)
    del bpy.types.Scene.aiagent_last_prompt
    for _name in ("aiagent_team_mode", "aiagent_smart_routing", "aiagent_memory", "aiagent_ask_mode"):
        if hasattr(bpy.types.Scene, _name):
            delattr(bpy.types.Scene, _name)
    del bpy.types.Scene.aiagent_last_reply
    del bpy.types.Scene.aiagent_last_reply_ok
    del bpy.types.Scene.aiagent_is_running
    del bpy.types.Scene.aiagent_status_text
    del bpy.types.Scene.aiagent_last_error
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
    _post_verifier = None
    _live_memory = None

if __name__ == "__main__":
    register()