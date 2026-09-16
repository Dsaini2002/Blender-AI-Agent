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
    """
    Hinglish: User ka text input Copilot Controller ko bhejta hai —
    LEKIN ab background thread mein, taaki Blender ki UI FREEZE na ho.

    Kaise kaam karta hai:
      1. execute() ek worker thread start karta hai jo controller.submit()
         chalata hai (LLM se baat karna — slow, network-bound part).
      2. Tool calls (bpy.ops.*) jab bhi aate hain, wo automatically
         MAIN THREAD pe marshal ho jaate hain (tool_caller.py +
         bridge/main_thread_dispatch.py ke through) — safe rehta hai.
      3. Modal operator ka apna TIMER (~20 baar/second) do kaam karta
         hai har tick pe: (a) pending bpy-dispatch requests process
         karta hai, (b) progress queue se status text update karta hai.
      4. Jab worker thread poora ho jaaye, modal() {'FINISHED'} return
         karta hai aur result dikhata hai.
    """

    bl_idname = "aiagent.copilot_submit"
    bl_label = "Send to Copilot"

    _thread = None
    _timer = None
    _progress_queue = None

    def execute(self, context):
        import queue
        import threading

        from .. import get_copilot_controller

        user_text = context.scene.aiagent_copilot_input
        if not user_text.strip():
            self.report({'WARNING'}, "Please enter a request first.")
            return {'CANCELLED'}

        controller = get_copilot_controller()
        self._progress_queue = queue.Queue()
        progress_queue = self._progress_queue  # closure ke liye local ref

        def on_progress(event, data):
            progress_queue.put(("progress", event))

        def worker():
            try:
                result = controller.submit(user_text, on_progress=on_progress)
                progress_queue.put(("done", result))
            except Exception as exc:  # noqa: BLE001
                progress_queue.put(("error", str(exc)))

        context.scene.aiagent_copilot_input = ""
        context.scene.aiagent_is_running = True
        context.scene.aiagent_status_text = "Starting..."

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        from ..bridge.main_thread_dispatch import drain_dispatch_queue

        drain_dispatch_queue()

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        try:
            while True:
                kind, payload = self._progress_queue.get_nowait()

                if kind == "progress":
                    context.scene.aiagent_status_text = payload
                    for area in context.screen.areas:
                        if area.type == 'VIEW_3D':
                            area.tag_redraw()

                elif kind == "done":
                    result = payload
                    if result.success:
                        self.report({'INFO'}, result.reply_text or "Done.")
                    else:
                        self.report({'ERROR'}, result.reply_text or "Task failed.")
                    return self._finish(context)

                elif kind == "error":
                    self.report({'ERROR'}, f"Unexpected error: {payload}")
                    return self._finish(context)
        except Exception:
            pass

        return {'PASS_THROUGH'}

    def _finish(self, context):
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
        context.scene.aiagent_is_running = False
        context.scene.aiagent_status_text = ""
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
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

        layout.label(text="AI Provider:")
        layout.prop(context.scene, "aiagent_provider_choice", text="")

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

        is_running = context.scene.aiagent_is_running
        row = layout.row()
        row.enabled = not is_running
        row.operator("aiagent.copilot_submit", icon='PLAY', text="Send")

        if is_running:
            box = layout.box()
            box.label(text="⏳ Working...", icon='TIME')
            status = context.scene.aiagent_status_text
            if status:
                box.label(text=status)

        layout.separator()
        layout.label(text="Debug Tools")
        layout.operator("aiagent.inspect_scene", icon='ZOOM_ALL')