"""
UI Panel — Copilot + Multi-Provider + Model Selection
==========================================================
Hinglish: Ab user Blender sidebar se hi AI provider AUR model
(jaise gemini-3.6-flash vs gemini-flash-latest) switch kar sakta hai.
"""

import bpy


class AIAGENT_OT_switch_provider(bpy.types.Operator):
    """Selected provider + model ke saath naya Copilot controller banata hai."""

    bl_idname = "aiagent.switch_provider"
    bl_label = "Switch AI Provider"

    def execute(self, context):
        from .. import get_copilot_controller

        provider_name = context.scene.aiagent_provider_choice
        # Hinglish: model_name sirf tab relevant hai jab provider = gemini
        # ya groq — har provider ka apna model dropdown hai. Mock provider
        # ke liye ise None rakho, warna "Switched to: mock (...)" jaisa
        # confusing message aata hai.
        model_name = None
        if provider_name == 'gemini':
            model_name = context.scene.aiagent_model_choice or None
        elif provider_name == 'groq':
            model_name = context.scene.aiagent_groq_model_choice or None

        get_copilot_controller(provider_name=provider_name, model_name=model_name)

        label = f"{provider_name}"
        if model_name:
            label += f" ({model_name})"
        self.report({'INFO'}, f"Switched to: {label}")
        return {'FINISHED'}


class AIAGENT_OT_copilot_submit(bpy.types.Operator):
    """User ka text input Copilot Controller ko bhejta hai."""

    bl_idname = "aiagent.copilot_submit"
    bl_label = "Send to Copilot"

    def execute(self, context):
        from .. import get_copilot_controller

        controller = get_copilot_controller()
        user_text = context.scene.aiagent_copilot_input

        if not user_text.strip():
            self.report({'WARNING'}, "Please enter a request first.")
            return {'CANCELLED'}

        result = controller.submit(user_text)

        if result.success:
            self.report({'INFO'}, result.reply_text or "Done.")
        else:
            self.report({'ERROR'}, result.reply_text or "Task failed.")

        context.scene.aiagent_copilot_input = ""
        return {'FINISHED'}


class AIAGENT_OT_inspect_scene(bpy.types.Operator):
    """Phase 1 ka original debug tool."""

    bl_idname = "aiagent.inspect_scene"
    bl_label = "Inspect Scene"

    def execute(self, context):
        import json
        from .. import get_registry

        registry = get_registry()
        tool = registry.get("scene.inspect")
        result = tool.execute()

        if result.success:
            print(json.dumps(result.data, indent=2))
            self.report({'INFO'}, "Scene inspected — check the System Console for JSON output.")
        else:
            self.report({'ERROR'}, f"Scene inspect failed: {result.error}")

        return {'FINISHED'}


class AIAgentPanel(bpy.types.Panel):
    """Sidebar (N-panel) mein AI Copilot ka panel."""

    bl_label = "AI Copilot"
    bl_idname = "AIAGENT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "AI Agent"

    def draw(self, context):
        from .. import get_copilot_controller

        layout = self.layout

        # Provider selection
        layout.label(text="AI Provider:")
        layout.prop(context.scene, "aiagent_provider_choice", text="")

        # Model selection — sirf relevant provider ke liye dikhega
        if context.scene.aiagent_provider_choice == 'gemini':
            layout.label(text="Model:")
            layout.prop(context.scene, "aiagent_model_choice", text="")
        elif context.scene.aiagent_provider_choice == 'groq':
            layout.label(text="Model:")
            layout.prop(context.scene, "aiagent_groq_model_choice", text="")

        layout.operator("aiagent.switch_provider", icon='FILE_REFRESH', text="Apply")

        controller = get_copilot_controller()
        current = getattr(controller, "current_provider_name", "mock")
        layout.label(text=f"Active: {current}", icon='CHECKMARK')

        layout.separator()

        layout.label(text="Ask the Copilot:")
        layout.prop(context.scene, "aiagent_copilot_input", text="")
        layout.operator("aiagent.copilot_submit", icon='PLAY', text="Send")

        layout.separator()
        layout.label(text="Debug Tools")
        layout.operator("aiagent.inspect_scene", icon='ZOOM_ALL')