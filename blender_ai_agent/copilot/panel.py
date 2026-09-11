"""
UI Panel — Step 6.6 (Copilot integration)
=============================================
Hinglish: Phase 1 mein ye panel sirf ek button tha jo directly
SceneInspectTool call karta tha. Ab Phase 6 mein ye CopilotController
se baat karta hai — UI business logic nahi rakhti, sirf user input
leke Controller ko forward karti hai (Step 6.1 ka rule).

    Panel -> CopilotController -> Agent -> ... -> Blender
"""

import bpy


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
    """Hinglish: Phase 1 ka original tool — backward-compatible rakha hai, standalone debugging ke liye."""

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
        layout = self.layout

        layout.label(text="Ask the Copilot:")
        layout.prop(context.scene, "aiagent_copilot_input", text="")
        layout.operator("aiagent.copilot_submit", icon='PLAY', text="Send")

        layout.separator()
        layout.label(text="Debug Tools")
        layout.operator("aiagent.inspect_scene", icon='ZOOM_ALL')