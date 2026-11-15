"""Progress sub-panel"""

import bpy

from ..copilot.step_progress import ascii_bar, format_duration, get_tracker
from .panel import _icon, run_in_progress

_STATUS_ICON = {"done": "CHECKMARK", "failed": "ERROR", "running": "PLAY", "pending": "DOT", "skipped": "X"}
_TIMER_REGISTERED = False
_REDRAW_INTERVAL = 0.5


def _clip(text: str, limit: int = 34) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _activity_text() -> str:
    try:
        from ..copilot.activity import get_text
        return get_text()
    except Exception:  # noqa: BLE001
        return ""


def _bar(layout, percent: float, text: str) -> None:
    if hasattr(layout, "progress"):
        layout.progress(factor=max(0.0, min(1.0, percent / 100.0)), type='BAR', text=text)
    else:
        layout.label(text=f"[{ascii_bar(percent, 14)}] {text}")


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
        activity = _activity_text() if running else ""

        if snap.total:
            percent = snap.percent or 0.0
            _bar(layout, percent, f"{percent:.0f}%")

            if running:
                layout.label(text=f"Step {snap.index}/{snap.total}: {_clip(snap.label)}", icon=_icon('TIME'))
                if activity:
                    layout.label(text=_clip(activity, 44), icon=_icon('SETTINGS'))
                layout.label(text=f"Elapsed {format_duration(snap.elapsed)}   ~{format_duration(snap.eta)} left")
            else:
                failed = f"  ({snap.failed} failed)" if snap.failed else ""
                layout.label(text=f"Done {snap.completed}/{snap.total}{failed} in {format_duration(snap.elapsed)}",
                             icon=_icon('CHECKMARK' if not snap.failed else 'ERROR'))

            box = layout.box()
            for number, step in enumerate(snap.steps, 1):
                row = box.row()
                row.label(text=f"{number}. {_clip(str(step['label']), 28)}", icon=_icon(_STATUS_ICON.get(str(step['status']), 'DOT')))
                seconds = step.get("seconds")
                if seconds is not None:
                    row.label(text=format_duration(seconds))
            return

        if running:
            typical = snap.typical or 0.0
            if typical > 0:
                estimate = min(95.0, 100.0 * snap.elapsed / typical)
                text = f"~{estimate:.0f}%" if snap.elapsed < typical else "Taking longer than usual…"
                _bar(layout, estimate, text)
            layout.label(text=f"Working… {format_duration(snap.elapsed)}", icon=_icon('TIME'))
            if activity:
                layout.label(text=_clip(activity, 44), icon=_icon('SETTINGS'))
            counters = []
            if snap.turns:
                counters.append(f"{snap.turns} AI turn(s)")
            if snap.tool_events:
                counters.append(f"{snap.tool_events} tool event(s)")
            if counters:
                layout.label(text=_clip("  ·  ".join(counters), 44))
            if typical > 0:
                layout.label(text=f"Usually takes ~{format_duration(typical)}")
        else:
            _bar(layout, 100.0, "100%" if snap.ok is not False else "Stopped")
            layout.label(text=f"Finished in {format_duration(snap.elapsed)}",
                         icon=_icon('CHECKMARK' if snap.ok is not False else 'ERROR'))


def _redraw_tick():
    """Redraw the sidebar while a task runs so the elapsed time keeps moving. Always returns a positive interval."""
    try:
        if get_tracker().is_running() or run_in_progress():
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
            return _REDRAW_INTERVAL
    except Exception:  # noqa: BLE001
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
