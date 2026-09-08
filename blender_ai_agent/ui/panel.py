"""
UI Panel
========
Hinglish: Phase 1 mein UI bahut simple hai — sirf ek button jo
"scene.inspect" tool run karke result console mein print karega.
"""

import json

import bpy


class AIAGENT_OT_inspect_scene(bpy.types.Operator):
    """Scene Inspector tool ko run karta hai aur result console mein print karta hai."""

    bl_idname = "aiagent.inspect_scene"
    bl_label = "Inspect Scene"

    def execute(self, context):
        # Lazy import taaki circular import na ho.
        from .. import get_registry

        registry = get_registry()
        tool = registry.get("scene.inspect")
        result = tool.execute()

        print(json.dumps(result, indent=2))
        self.report({'INFO'}, "Scene inspected — check the System Console for JSON output.")
        return {'FINISHED'}


class AIAgentPanel(bpy.types.Panel):
    """Sidebar (N-panel) mein AI Agent ka panel."""

    bl_label = "AI Agent (Phase 1)"
    bl_idname = "AIAGENT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "AI Agent"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Deterministic Foundation")
        layout.operator("aiagent.inspect_scene", icon='ZOOM_ALL')