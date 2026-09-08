import json

import bpy


class AIAGENT_OT_inspect_scene(bpy.types.Operator):
    bl_idname = "aiagent.inspect_scene"
    bl_label = "Inspect Scene"

    def execute(self, context):
        from .. import get_registry

        registry = get_registry()
        tool = registry.get("scene.inspect")
        result = tool.execute()  # ab ye ToolResult hai, dict nahi

        if result.success:
            print(json.dumps(result.data, indent=2))
            self.report({'INFO'}, "Scene inspected — check the System Console for JSON output.")
        else:
            print(f"[AI Agent] Tool failed: {result.error}")
            self.report({'ERROR'}, f"Scene inspect failed: {result.error}")

        return {'FINISHED'}


class AIAgentPanel(bpy.types.Panel):
    bl_label = "AI Agent (Phase 1)"
    bl_idname = "AIAGENT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "AI Agent"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Deterministic Foundation")
        layout.operator("aiagent.inspect_scene", icon='ZOOM_ALL')