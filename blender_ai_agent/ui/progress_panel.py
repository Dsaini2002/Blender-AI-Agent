"""
Progress sub-panel — AI Copilot panel ke andar "Progress" section
====================================================================
Hinglish: Ye ek alag chhota panel hai (parent = "AIAGENT_PT_panel"), isliye purane ui/panel.py ko chhedna nahi
padta. Ye copilot/step_progress.py ke tracker se padhta hai (tracker worker thread mein update hota hai, ye main thread
mein sirf draw karta hai).

Dikhata hai:
  - progress bar + percent
  - "Step 2/5: <kaam>"
  - Elapsed aur ETA ("~0:52 baaki")
  - har step ki list: ✓ done, ! failed, ▶ chal raha, · baaki

Elapsed time har second badhe, isliye ek halka timer (1 sec) UI ko redraw karwata rehta hai jab task chal raha ho.
"""

import bpy

from ..copilot.step_progress import ascii_bar, format_duration, get_tracker

_STATUS_ICON = {"done": "CHECKMARK", "failed": "ERROR", "running": "PLAY", "pending": "DOT", "skipped": "X"}
_TIMER_REGISTERED = False


def _clip(text: str, limit: int = 34) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


class AIAGENT_PT_progress(bpy.types.Panel):
    bl_label = "Progress"
    bl_idname = "AIAGENT_PT_progress"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "AI Agent"
    bl_parent_id = "AIAGENT_PT_panel"

    @classmethod
    def poll(cls, context):
        return get_tracker().snapshot().state != "idle"

    def draw(self, context):
        layout = self.layout
        snap = get_tracker().snapshot()
        running = snap.state == "running"

        if snap.total:
            percent = snap.percent or 0.0
            text = f"{percent:.0f}%"
            if hasattr(layout, "progress"):                                   # Blender 4.0+ ka asli progress bar
                layout.progress(factor=percent / 100.0, type='BAR', text=text)
            else:
                layout.label(text=f"[{ascii_bar(percent, 14)}] {text}")

            if running:
                layout.label(text=f"Step {snap.index}/{snap.total}: {_clip(snap.label)}", icon='TIME')
                layout.label(text=f"Elapsed {format_duration(snap.elapsed)}   ~{format_duration(snap.eta)} left")
            else:
                failed = f"  ({snap.failed} failed)" if snap.failed else ""
                layout.label(text=f"Done {snap.completed}/{snap.total}{failed} in {format_duration(snap.elapsed)}",
                             icon='CHECKMARK' if not snap.failed else 'ERROR')

            box = layout.box()
            for number, step in enumerate(snap.steps, 1):
                row = box.row()
                row.label(text=f"{number}. {_clip(str(step['label']), 28)}", icon=_STATUS_ICON.get(str(step['status']), 'DOT'))
                seconds = step.get("seconds")
                if seconds is not None:
                    row.label(text=format_duration(seconds))
        else:                                                                 # single task
            if running:
                layout.label(text=f"Working… {format_duration(snap.elapsed)}", icon='TIME')
                layout.label(text=f"Usually takes ~{format_duration(snap.typical)}")
            else:
                layout.label(text=f"Finished in {format_duration(snap.elapsed)}",
                             icon='CHECKMARK' if snap.ok else 'ERROR')


def _redraw_tick():
    """Task chalte waqt har second UI redraw taaki elapsed/ETA badhte dikhein. Hamesha 1.0 return = chalta rahe."""
    try:
        if get_tracker().is_running():
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
    except Exception:  # noqa: BLE001 — timer kabhi Blender ko na giraye
        pass
    return 1.0


def register_progress_timer():
    global _TIMER_REGISTERED
    if not _TIMER_REGISTERED:
        bpy.app.timers.register(_redraw_tick, first_interval=1.0, persistent=True)
        _TIMER_REGISTERED = True


def unregister_progress_timer():
    global _TIMER_REGISTERED
    if _TIMER_REGISTERED:
        try:
            bpy.app.timers.unregister(_redraw_tick)
        except ValueError:
            pass
        _TIMER_REGISTERED = False