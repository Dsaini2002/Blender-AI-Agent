"""UI Panel — AI Copilot (sidebar > "AI Agent" tab)"""

import os
import re
import textwrap

import bpy

PROVIDERS = {
    "gemini": ("Google Gemini", "GEMINI_API_KEY", "aiagent_model_choice"),
    "claude": ("Anthropic Claude", "ANTHROPIC_API_KEY", "aiagent_claude_model_choice"),
    "openai": ("OpenAI", "OPENAI_API_KEY", "aiagent_openai_model_choice"),
}

_PREVIEW_LINES = 8

MAX_PREVIEW_LINES = 10
PROMPT_BOX_ROWS = 12          # the prompt box grows with the text up to this many lines, then it scrolls


def prompt_text(scene) -> str:
    """The current prompt."""
    return (getattr(scene, "aiagent_copilot_input", "") or "").strip()


def set_prompt(scene, text: str) -> None:
    """Replace the prompt (Paste / Clear / after Generate)."""
    try:
        scene.aiagent_copilot_input = text or ""
    except Exception:  # noqa: BLE001
        pass
    sync_prompt_lines(scene)


# ----------------------------------------------------------------------------- the prompt box (grows, then scrolls)
_BOX = {"width": 40}


def prompt_box_lines(text: str, width: int):
    """The prompt as the lines the box shows (wrapped to the panel width; empty lines kept)."""
    return _wrap(_clean_text(text), max(12, width)) if (text or "").strip() else []


def sync_prompt_lines(scene, width: int = 0) -> None:
    """Copy the prompt into the box's line list. Only from operators / update callbacks / timers - Blender does
    not allow writing scene data while a panel draws."""
    lines_prop = getattr(scene, "aiagent_prompt_lines", None)
    if lines_prop is None:
        return
    width = width or _BOX["width"]
    _BOX["width"] = width
    try:
        lines = prompt_box_lines(prompt_text(scene), width)
        if [item.text for item in lines_prop] == lines:
            return
        lines_prop.clear()
        for line in lines:
            lines_prop.add().text = line
        scene.aiagent_prompt_line_index = -1
    except Exception:  # noqa: BLE001
        pass


def _resync_later(width: int) -> None:
    """The panel became wider / narrower: re-wrap the box after this draw."""
    if _BOX.get("pending") == width:
        return
    _BOX["pending"] = width

    def _later():
        _BOX.pop("pending", None)
        try:
            for scene in bpy.data.scenes:
                sync_prompt_lines(scene, width)
            _redraw()
        except Exception:  # noqa: BLE001
            pass
        return None
    try:
        bpy.app.timers.register(_later, first_interval=0.0)
    except Exception:  # noqa: BLE001
        _BOX.pop("pending", None)




def _bool_prop(**kwargs):
    props = getattr(bpy, "props", None)
    return props.BoolProperty(**kwargs) if props is not None else None


def _prop(kind: str, **kwargs):
    """bpy.props.<kind>(...) - or None where bpy.props does not exist (the tests' stand-in bpy)."""
    props = getattr(bpy, "props", None)
    return getattr(props, kind)(**kwargs) if props is not None else None


# ----------------------------------------------------------------------------- small helpers
def _set_last_error(scene, message):
    try:
        scene.aiagent_last_error = message
    except AttributeError:
        pass


def _set_reply(scene, text: str, ok: bool) -> None:
    try:
        scene.aiagent_last_reply = (text or "").strip()
        scene.aiagent_last_reply_ok = bool(ok)
    except AttributeError:
        pass
    _set_last_error(scene, "" if ok else (text or ""))


class AIAGENT_PromptLine(getattr(bpy.types, "PropertyGroup", object)):
    """One line of the prompt box."""
    text: _prop("StringProperty", name="Line", default="")


class AIAGENT_UL_prompt_lines(getattr(bpy.types, "UIList", object)):
    """The prompt box: every line of the prompt, its own scroll bar once it is longer than the box."""
    bl_idname = "AIAGENT_UL_prompt_lines"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index=0, flt_flag=0):
        layout.label(text=item.text or " ")

    def draw_filter(self, context, layout):
        pass


def _clean_text(text: str) -> str:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    lines = [line.rstrip() for line in text.split("\n")]
    cleaned, blank = [], 0
    for line in lines:
        blank = blank + 1 if not line else 0
        if blank <= 1:
            cleaned.append(line)
    return "\n".join(cleaned).strip()


def recover_cut_paste(prompt: str, clipboard: str) -> str:
    """Blender's one-line text field keeps only the FIRST line when a multi-line text is pasted with Ctrl+V.
    If the prompt is exactly that first line and the clipboard holds more, the user meant the whole text."""
    prompt, clip = _clean_text(prompt), _clean_text(clipboard)
    if not prompt or not clip or "\n" not in clip:
        return prompt
    first = next((line.strip() for line in clip.split("\n") if line.strip()), "")
    if prompt.strip() == first and len(clip) > len(prompt):
        return clip
    return prompt


def _chars_per_line(context, fallback: int = 40) -> int:
    try:
        width = context.region.width
        scale = context.preferences.view.ui_scale
        return max(18, min(220, int((width - 46) / (6.4 * scale))))
    except Exception:  # noqa: BLE001
        return fallback


def _wrap(text: str, width: int):
    lines = []
    for paragraph in (text or "").split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        lines.extend(textwrap.wrap(paragraph, width=width, break_long_words=True, replace_whitespace=False) or [""])
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _draw_wrapped(layout, text: str, width: int, max_lines: int = 0, icon: str = 'NONE') -> int:
    lines = _wrap(text, width)
    hidden = 0
    if max_lines and len(lines) > max_lines:
        hidden = len(lines) - max_lines
        lines = lines[:max_lines]
    col = layout.column(align=True)
    col.scale_y = 0.85
    for index, line in enumerate(lines):
        col.label(text=line or " ", icon=_icon(icon if index == 0 else 'BLANK1' if icon != 'NONE' else 'NONE'))
    return hidden


_ICONS = None


def _op(layout, idname: str, **kwargs):
    module, _, name = idname.partition(".")
    registered = True
    try:
        registered = hasattr(getattr(bpy.ops, module), name) and bool(getattr(getattr(bpy.ops, module), name).idname())
    except Exception:  # noqa: BLE001 
        registered = True
    if not registered:
        return None
    try:
        return layout.operator(idname, **kwargs)
    except Exception:  # noqa: BLE001
        return None


def _set_op_prop(op, name: str, value) -> None:
    if op is not None:
        try:
            setattr(op, name, value)
        except Exception:  # noqa: BLE001
            pass


def _icon(name: str) -> str:
    global _ICONS
    if _ICONS is None:
        try:
            _ICONS = set(bpy.types.UILayout.bl_rna.functions["label"].parameters["icon"].enum_items.keys())
        except Exception:  # noqa: BLE001 
            _ICONS = set()
    if not _ICONS or name in _ICONS:
        return name
    return 'NONE'


def _draw_prompt_box(layout, scene, width: int) -> None:
    """The prompt: a tall text field plus the whole text wrapped below it (Blender has no multi-line
    text box in a side panel, so a pasted multi-line prompt is shown line by line here)."""
    box = layout.box()
    col = box.column()
    field = col.row()
    field.scale_y = 1.9
    if _supports_placeholder():
        field.prop(scene, "aiagent_copilot_input", text="", placeholder="Describe what to create or modify…")
    else:
        field.prop(scene, "aiagent_copilot_input", text="")
    text = prompt_text(scene)
    wrap_width = max(12, width - 6)
    if abs(wrap_width - _BOX["width"]) > 2:
        _resync_later(wrap_width)
    lines_prop = getattr(scene, "aiagent_prompt_lines", None)
    if text and lines_prop is not None and len(lines_prop):
        # the whole prompt: grows line by line, scrolls (mouse wheel / scroll bar) after PROMPT_BOX_ROWS lines
        rows = max(1, min(len(lines_prop), PROMPT_BOX_ROWS))
        col.template_list("AIAGENT_UL_prompt_lines", "", scene, "aiagent_prompt_lines", scene,
                          "aiagent_prompt_line_index", rows=rows, maxrows=PROMPT_BOX_ROWS)
    elif text and ("\n" in text or len(text) > width - 4):
        preview = box.column(align=True)                 # (no line list: older files) the text wrapped below
        preview.scale_y = 0.8
        lines = _wrap(text, wrap_width)
        hidden = max(0, len(lines) - MAX_PREVIEW_LINES)
        for line in lines[:MAX_PREVIEW_LINES]:
            preview.label(text=line or " ")
        if hidden:
            preview.label(text=f"… +{hidden} more line(s)")
    tools = box.row(align=True)
    _set_op_prop(_op(tools, "aiagent.prompt_paste", text="Paste", icon=_icon('PASTEDOWN')), 'append', False)
    hint = tools.row()
    hint.alignment = 'RIGHT'
    count = len(lines_prop) if lines_prop is not None else 0
    hint.label(text=(f"{count} line(s) · {len(text)} chars" if text else "Ctrl+V pastes all lines"))


_PLACEHOLDER = {}


def _supports_placeholder() -> bool:
    """UILayout.prop(placeholder=...) exists in newer Blender versions only."""
    if "ok" not in _PLACEHOLDER:
        try:
            params = bpy.types.UILayout.bl_rna.functions["prop"].parameters
            _PLACEHOLDER["ok"] = "placeholder" in params.keys()
        except Exception:  # noqa: BLE001
            _PLACEHOLDER["ok"] = False
    return _PLACEHOLDER["ok"]


_PROMPT_GUARD = {"busy": False}


def on_prompt_changed(self, context):
    """Ctrl+V in Blender's one-line field keeps only the first line of a multi-line clipboard: put the whole
    text in instead, right away, so the preview shows every line."""
    if _PROMPT_GUARD["busy"]:
        return
    try:
        clipboard = context.window_manager.clipboard
        current = self.aiagent_copilot_input
    except Exception:  # noqa: BLE001
        return
    full = recover_cut_paste(current, clipboard)
    if full != _clean_text(current):
        _PROMPT_GUARD["busy"] = True
        try:
            self.aiagent_copilot_input = full
        finally:
            _PROMPT_GUARD["busy"] = False
    sync_prompt_lines(self)


_RUN = {"start": None, "seconds": None}


def run_in_progress() -> bool:
    return _RUN["start"] is not None and _RUN["seconds"] is None


def _run_started() -> None:
    import time
    _RUN["start"], _RUN["seconds"] = time.monotonic(), None


def _run_finished() -> None:
    import time
    if _RUN["start"] is not None:
        _RUN["seconds"] = time.monotonic() - _RUN["start"]


def _working_text() -> str:
    try:
        import time
        from ..copilot.step_progress import format_duration, get_tracker
        snap = get_tracker().snapshot()
        elapsed = time.monotonic() - _RUN["start"] if _RUN["start"] is not None else snap.elapsed
        text = f"Working… {format_duration(elapsed)}"
        if snap.state == "done":
            text = f"Checking the result… {format_duration(elapsed)}"
        provider = getattr(getattr(_controller_or_none(), "_agent", None), "_model_provider", None)
        tier = getattr(getattr(provider, "last_tier", None), "value", None)
        if tier:
            text += f"  ·  {tier} model"
        if snap.total and snap.state == "running":
            text += f"  ·  step {snap.index}/{snap.total}"
        return text
    except Exception:  # noqa: BLE001
        return "Working…"


def _finished_text(word: str) -> str:
    """'Completed in 4:02' — total time of the whole request, including the automatic check."""
    try:
        from ..copilot.step_progress import format_duration
        if _RUN["seconds"] is not None:
            return f"{word} in {format_duration(_RUN['seconds'])}"
    except Exception:  # noqa: BLE001
        pass
    return word


def _safe_draw(panel, context, body) -> None:
    try:
        body(context)
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        box = panel.layout.box()
        box.alert = True
        box.label(text="Panel error (see Window > Toggle System Console):", icon=_icon('ERROR'))
        for line in textwrap.wrap(f"{type(exc).__name__}: {exc}", 40)[:6]:
            box.label(text=line)


def _redraw(context=None) -> None:
    try:
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
    except Exception:  # noqa: BLE001
        pass


def _has_key(provider: str) -> bool:
    info = PROVIDERS.get(provider)
    if not info:
        return False
    if not os.environ.get(info[1], ""):
        # Blender may not hand out the add-on preferences during register(); pick a saved key up here
        try:
            from ..prefs import apply_keys
            apply_keys()
        except Exception:  # noqa: BLE001
            pass
    return bool(os.environ.get(info[1], ""))


def _selected_model(scene, provider: str):
    info = PROVIDERS.get(provider)
    if info is None:
        return None
    return getattr(scene, info[2], None) or None


def _controller_or_none():
    try:
        from .. import get_copilot_controller
        return get_copilot_controller()
    except Exception:  # noqa: BLE001 
        return None


def _apply_provider(scene) -> str:
    from .. import get_copilot_controller

    provider = scene.aiagent_provider_choice
    label, env_var, _ = PROVIDERS.get(provider, (provider, "", ""))
    if not _has_key(provider):
        return f"{label}: no API key yet — click the gear, paste your key and press Connect."
    model = _selected_model(scene, provider)
    from .. import get_provider_registry, refresh_provider_registry
    if provider not in get_provider_registry().list_providers():
        refresh_provider_registry()          # its key arrived after the providers were built: read the keys again
    get_copilot_controller(provider_name=provider, model_name=model)
    return f"Connected to {label}" + (f" · {model}" if model else "")


SWITCH_NOTE = {"text": "", "error": False}

_USAGE_CACHE = {"time": 0.0, "key": "", "text": ""}


def _today_usage(provider: str, model: str) -> str:
    """'Today (gemini gemini-3.6-flash): 18 request(s), 312,400 tokens' - read at most every 3 s (the panel redraws a lot)."""
    import time as _time
    key = f"{provider} {model}"
    if _USAGE_CACHE["key"] == key and _time.time() - _USAGE_CACHE["time"] < 3.0:
        return _USAGE_CACHE["text"]
    try:
        from ..observability.token_meter import today_text
        text = today_text(provider, model)
    except Exception:  # noqa: BLE001
        text = ""
    _USAGE_CACHE.update(time=_time.time(), key=key, text=text)
    return text


def use_panel_choice(scene, controller):
    """Generate always uses the provider + model shown in the panel's top row. (After a quota error the Copilot
    may have moved on to another AI - the next Generate goes back to the one picked; picking the one already
    shown fires no change in Blender, so this is the only place that can do it.)"""
    wanted = getattr(scene, "aiagent_provider_choice", "") or ""
    if not wanted or not _has_key(wanted):
        return controller
    model = _selected_model(scene, wanted)
    current = getattr(controller, "current_provider_name", "mock")
    if current == wanted and (not model or getattr(controller, "current_model_name", None) in (None, model)):
        return controller
    try:
        SWITCH_NOTE.update(text=_apply_provider(scene), error=False)
        return _controller_or_none() or controller
    except Exception as exc:  # noqa: BLE001
        SWITCH_NOTE.update(text=f"Could not switch: {exc}", error=True)
        return controller


def on_provider_changed(self, context):
    """Provider / model picked in the panel (top row or settings): connect it right away."""
    scene = context.scene if context is not None else None
    if scene is None:
        return
    if getattr(scene, "aiagent_is_running", False):
        SWITCH_NOTE.update(text="Busy - the new choice is used after this run (or press Stop).", error=True)
        return
    try:
        message = _apply_provider(scene)
        SWITCH_NOTE.update(text=message, error=not message.startswith("Connected"))
    except Exception as exc:  # noqa: BLE001
        SWITCH_NOTE.update(text=f"Could not switch: {exc}", error=True)
        print(f"[Blender AI Agent] Could not switch provider: {exc}")


# ============================================================================= operators
class AIAGENT_OT_switch_provider(bpy.types.Operator):
    """Connect the selected AI provider and model"""

    bl_idname = "aiagent.switch_provider"
    bl_label = "Connect"

    def execute(self, context):
        if context.scene.aiagent_is_running:
            self.report({'WARNING'}, "Wait for the current task to finish.")
            return {'CANCELLED'}
        try:
            message = _apply_provider(context.scene)
        except Exception as exc:  # noqa: BLE001
            self.report({'ERROR'}, f"Could not connect: {exc}")
            return {'CANCELLED'}
        level = {'INFO'} if message.startswith("Connected") else {'WARNING'}
        self.report(level, message)
        return {'FINISHED'}


KEY_PREFIXES = {"gemini": ("AIza",), "claude": ("sk-ant-",), "openai": ("sk-",)}


def key_warning(provider: str, key: str) -> str:
    """A short warning when a pasted key does not look like this provider's key (it is saved anyway)."""
    key = (key or "").strip()
    if not key:
        return "The key is empty."
    if " " in key:
        return "The key has a space in it - copy it again."
    prefixes = KEY_PREFIXES.get(provider)
    if prefixes and not key.startswith(prefixes):
        return f"This does not look like a {PROVIDERS.get(provider, (provider,))[0]} key (it usually starts with {prefixes[0]})."
    return ""


def save_key(scene, provider: str, key: str) -> str:
    """Store the key for `provider` (Blender preferences + this session), then connect. Returns a message."""
    key = (key or "").strip()
    if not key:
        return "Paste the key first."
    from ..prefs import PROVIDER_KEY, apply_keys, get_prefs, remember_key, _save_preferences_soon
    entry = PROVIDER_KEY.get(provider)
    if entry is None:
        return f"Unknown provider '{provider}'."
    prop, env, label, _url = entry
    remember_key(env, key)                 # asked once: a new version of the add-on finds it again
    prefs = get_prefs()
    if prefs is not None:
        setattr(prefs, prop, key)                      # its update callback applies it too
        apply_keys(prefs)
        _save_preferences_soon()
    else:
        os.environ[env] = key
    try:
        from .. import reset_providers
        reset_providers()
    except Exception:  # noqa: BLE001
        pass
    warning = key_warning(provider, key)
    try:
        message = _apply_provider(scene)
    except Exception as exc:  # noqa: BLE001
        message = f"{label} key saved, but connecting failed: {exc}"
    return message + (f" ({warning})" if warning else "")


class AIAGENT_OT_save_key(bpy.types.Operator):
    """Save the API key for the chosen AI provider and connect"""

    bl_idname = "aiagent.save_key"
    bl_label = "Submit Key"

    def execute(self, context):
        scene = context.scene
        if scene.aiagent_is_running:
            self.report({'WARNING'}, "Wait for the current task to finish.")
            return {'CANCELLED'}
        key = getattr(scene, "aiagent_key_input", "") or ""
        if not key.strip():
            self.report({'WARNING'}, "Paste the API key into the box first.")
            return {'CANCELLED'}
        message = save_key(scene, scene.aiagent_provider_choice, key)
        try:
            scene.aiagent_key_input = ""                     # never keep the key in the .blend file
            scene.aiagent_change_key = False
        except AttributeError:
            pass
        self.report({'INFO'} if message.startswith("Connected") else {'WARNING'}, message)
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_prompt_paste(bpy.types.Operator):

    bl_idname = "aiagent.prompt_paste"
    bl_label = "Paste"
    bl_options = {'INTERNAL'}

    append: _bool_prop(name="Append", description="Add to the end of the prompt instead of replacing it",
                       default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        clip = _clean_text(context.window_manager.clipboard)
        if not clip:
            self.report({'WARNING'}, "Clipboard is empty.")
            return {'CANCELLED'}
        scene = context.scene
        current = prompt_text(scene).rstrip()
        set_prompt(scene, f"{current}\n{clip}" if (self.append and current) else clip)   # (fills the box too)
        lines = clip.count("\n") + 1
        self.report({'INFO'}, f"Pasted {len(clip)} characters ({lines} line{'s' if lines != 1 else ''}).")
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_prompt_copy(bpy.types.Operator):

    bl_idname = "aiagent.prompt_copy"
    bl_label = "Copy Prompt"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        text = prompt_text(context.scene)
        if not text.strip():
            self.report({'WARNING'}, "The prompt is empty.")
            return {'CANCELLED'}
        context.window_manager.clipboard = text
        self.report({'INFO'}, "Prompt copied.")
        return {'FINISHED'}


class AIAGENT_OT_prompt_clear(bpy.types.Operator):
    """Clear the prompt"""

    bl_idname = "aiagent.prompt_clear"
    bl_label = "Clear Prompt"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        set_prompt(context.scene, "")
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_reply_copy(bpy.types.Operator):

    bl_idname = "aiagent.reply_copy"
    bl_label = "Copy Response"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        text = getattr(context.scene, "aiagent_last_reply", "")
        if not text:
            self.report({'WARNING'}, "No response yet.")
            return {'CANCELLED'}
        context.window_manager.clipboard = text
        self.report({'INFO'}, "Response copied.")
        return {'FINISHED'}


class AIAGENT_OT_reply_clear(bpy.types.Operator):
    """Clear the last response"""

    bl_idname = "aiagent.reply_clear"
    bl_label = "Clear Response"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        _set_reply(context.scene, "", True)
        try:
            context.scene.aiagent_last_prompt = ""
        except AttributeError:
            pass
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_approve(bpy.types.Operator):
    """Answer the AI's question (allow or deny the risky step)"""

    bl_idname = "aiagent.approve"
    bl_label = "Answer"
    bl_options = {'INTERNAL'}

    allow: _bool_prop(name="Allow", default=False, options={'SKIP_SAVE'})
    allow_all: _bool_prop(name="Allow all", default=False, options={'SKIP_SAVE'})

    def execute(self, context):
        from ..copilot.approval import get_gate
        if self.allow_all:
            get_gate().allow_all()
        else:
            get_gate().answer(self.allow)
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_memory_forget(bpy.types.Operator):
    """Forget everything the Copilot remembered (preferences and past builds)"""

    bl_idname = "aiagent.memory_forget"
    bl_label = "Forget Memory"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        try:
            from .. import get_live_memory
            get_live_memory().forget_all()
        except Exception as exc:  # noqa: BLE001
            self.report({'ERROR'}, f"Could not clear memory: {exc}")
            return {'CANCELLED'}
        self.report({'INFO'}, "Memory cleared.")
        return {'FINISHED'}


_WORKER = {"thread": None, "controller": None}


def worker_alive() -> bool:
    thread = _WORKER.get("thread")
    return bool(thread is not None and thread.is_alive())


def stop_background_run() -> None:
    controller = _WORKER.get("controller")
    if controller is not None:
        try:
            controller.cancel()
        except Exception:  # noqa: BLE001
            pass


def checks_folder() -> str:
    return os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "checks")


def latest_check_round() -> str:
    """The newest checks/<time>_r<round> folder (images + review.txt + fix_prompt.txt), or ''."""
    root = checks_folder()
    try:
        rounds = sorted((d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))), reverse=True)
    except OSError:
        return ""
    return os.path.join(root, rounds[0]) if rounds else ""


class AIAGENT_OT_open_checks(bpy.types.Operator):
    """Open the folder of the latest automatic check: the images the vision reviewer saw, review.txt (what it found)
    and fix_prompt.txt (what the agent was told to fix)"""

    bl_idname = "aiagent.open_checks"
    bl_label = "Check Images"

    def execute(self, context):
        folder = latest_check_round()
        if not folder:
            self.report({'WARNING'}, "No automatic check has run yet.")
            return {'CANCELLED'}
        review = os.path.join(folder, "review.txt")
        try:
            bpy.ops.wm.path_open(filepath=folder)
            if os.path.isfile(review):
                bpy.ops.wm.path_open(filepath=review)
        except Exception as exc:  # noqa: BLE001
            self.report({'WARNING'}, f"Open it yourself: {folder} ({exc})")
            return {'CANCELLED'}
        return {'FINISHED'}


class AIAGENT_OT_find_errors(bpy.types.Operator):
    """Find every problem in the scene (overlaps, through walls, floating, camera, lights, materials, sizes,
    missing things ...) and write it to ~/BlenderAIAgent/errors/<time>_errors.txt. Changes nothing in the scene"""

    bl_idname = "aiagent.find_errors"
    bl_label = "Find Errors"

    def execute(self, context):
        from .. import get_bridge
        from ..diagnostics.scene_audit import write_errors
        request = getattr(context.scene, "aiagent_last_prompt", "") or getattr(context.scene, "aiagent_prompt", "")
        try:
            path = write_errors(get_bridge(), request=request)
        except Exception as exc:  # noqa: BLE001
            self.report({'ERROR'}, f"Error finder failed: {type(exc).__name__}: {exc}")
            return {'CANCELLED'}
        try:
            first = open(path, encoding="utf-8").read().splitlines()[3]
            self.report({'INFO'}, f"{first.strip()} -> {path}")
            bpy.ops.wm.path_open(filepath=path)
        except Exception:  # noqa: BLE001
            self.report({'INFO'}, f"Written: {path}")
        return {'FINISHED'}


class AIAGENT_OT_copilot_stop(bpy.types.Operator):

    bl_idname = "aiagent.copilot_stop"
    bl_label = "Stop"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            from ..copilot import activity
            activity.abandon()             # every AI wait, tool call and render of the run ends now
        except Exception:  # noqa: BLE001
            pass
        stop_background_run()
        controller = _controller_or_none()
        if controller is not None:
            controller.cancel()
        try:
            from ..copilot.approval import get_gate
            get_gate().answer(False)
        except Exception:  # noqa: BLE001
            pass
        try:
            from ..copilot.activity import set_text
            set_text("Stopped.")
        except Exception:  # noqa: BLE001
            pass
        context.scene.aiagent_status_text = "Stopped."
        self.report({'INFO'}, "Stopped. What was built so far stays (Revert AI Changes undoes it).")
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_copilot_submit(bpy.types.Operator):


    bl_idname = "aiagent.copilot_submit"
    bl_label = "Generate"

    _thread = None
    _timer = None
    _progress_queue = None

    @classmethod
    def poll(cls, context):
        return not context.scene.aiagent_is_running

    def execute(self, context):
        import queue
        import threading

        from ..copilot import activity
        from ..copilot.step_progress import get_tracker

        scene = context.scene
        user_text = _clean_text(prompt_text(scene))
        if not user_text:
            self.report({'WARNING'}, "Type or paste a prompt first.")
            return {'CANCELLED'}
        try:
            full = recover_cut_paste(user_text, context.window_manager.clipboard)
        except Exception:  # noqa: BLE001
            full = user_text
        if full != user_text:
            user_text = full
            set_prompt(scene, full)
            self.report({'INFO'}, f"Using the whole pasted text ({full.count(chr(10)) + 1} lines).")

        if worker_alive():
            # an earlier run is still going in the background (e.g. after File > New, or waiting for the AI):
            # two runs at once on one scene broke a whole villa build
            stop_background_run()
            self.report({'WARNING'}, "The previous run is still finishing in the background - it was told to stop. "
                                     "Press Generate again in a few seconds.")
            return {'CANCELLED'}
        controller = _controller_or_none()
        if controller is None:
            self.report({'ERROR'}, "The Copilot could not start — see the System Console.")
            return {'CANCELLED'}
        selected = getattr(scene, "aiagent_provider_choice", "") or ""
        if selected and not _has_key(selected):
            label = PROVIDERS.get(selected, (selected,))[0]
            message = (f"No {label} API key added yet. Paste your key in the key box in the AI Copilot panel and "
                       f"press Submit Key, then press Generate again.")
            _set_reply(scene, message, False)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        controller = use_panel_choice(scene, controller)
        if getattr(controller, "current_provider_name", "mock") == "mock":
            message = "No AI provider connected. Paste an API key in the panel (⚙) or in Edit > Preferences > Add-ons."
            _set_reply(scene, message, False)
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        shown_prompt = user_text
        if getattr(scene, "aiagent_scene_context", True):
            from .run_state import with_scene_context
            active = getattr(getattr(context, "active_object", None), "name", None)
            user_text = with_scene_context(user_text, _selected_names(context), active)
        try:
            from .. import get_bridge
            from .run_state import take_checkpoint
            take_checkpoint(get_bridge(), shown_prompt)
        except Exception as exc:  # noqa: BLE001 — never block a run because the checkpoint failed
            print(f"[Blender AI Agent] checkpoint skipped: {exc}")
        activity.begin_run()
        _run_started()
        controller.memory_enabled = True
        controller.team_enabled = True
        if getattr(controller, "_cancelled", False):
            controller._cancelled = False

        try:
            from .. import get_tool_caller
            get_tool_caller().approver = None                 # no permission prompts: every step runs
        except Exception:  # noqa: BLE001
            pass

        tracker = get_tracker()
        self._progress_queue = queue.Queue()
        progress_queue = self._progress_queue

        def on_progress(event, data=None):
            try:
                activity.update(event, data)
                tracker.note_event(event)
            except Exception:  # noqa: BLE001
                pass
            progress_queue.put(("progress", str(event)))

        def worker():
            try:
                result = controller.submit(user_text, on_progress=on_progress)
                progress_queue.put(("done", result))
            except Exception as exc:  # noqa: BLE001
                progress_queue.put(("error", str(exc)))
            finally:
                try:
                    activity.run_thread_ended()
                except Exception:  # noqa: BLE001
                    pass

        try:
            scene.aiagent_last_prompt = shown_prompt
        except AttributeError:
            pass
        set_prompt(scene, "")
        _set_reply(scene, "", True)
        scene.aiagent_is_running = True
        scene.aiagent_status_text = "Starting…"
        activity.set_text("Starting")

        self._thread = threading.Thread(target=worker, name="AIAgentCopilot", daemon=True)
        self._thread.start()
        _WORKER.update(thread=self._thread, controller=controller)

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        _redraw(context)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        import queue

        from ..bridge.main_thread_dispatch import drain_dispatch_queue

        drain_dispatch_queue()

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        try:
            from ..copilot import activity
            stopped = activity.should_stop()
        except Exception:  # noqa: BLE001
            stopped = False
        if stopped:
            # Stop pressed: the panel is free at once; the run's thread ends at its next AI answer / tool call /
            # render without changing anything more
            message = "Stopped. What was built so far stays in the scene (Revert AI Changes undoes it)."
            _set_reply(context.scene, message, False)
            self.report({'INFO'}, message)
            return self._finish(context, message, False, stopped=True)

        changed = False
        while True:
            try:
                kind, payload = self._progress_queue.get_nowait()
            except queue.Empty:
                break

            if kind == "progress":
                context.scene.aiagent_status_text = payload
                changed = True
            elif kind == "done":
                return self._finish_with_result(context, payload)
            elif kind == "error":
                return self._finish_with_error(context, payload)

        try:
            from ..copilot.approval import get_gate
            question = get_gate().pending_question()
        except Exception:  # noqa: BLE001
            question = None
        if question != getattr(self, "_shown_question", None):
            self._shown_question = question
            changed = True
        if changed:
            _redraw(context)
        return {'PASS_THROUGH'}

    def _finish_with_result(self, context, result):
        from ..reliability.friendly_errors import friendly_error_message

        if result.success:
            reply, ok = result.reply_text or "Done.", True
            self.report({'INFO'}, "Copilot: done.")
        elif getattr(result, "status", "") == "partial":
            reply, ok = result.reply_text or "Partly done.", False       # honest: not shown as a success
            self.report({'WARNING'}, "Copilot: partly done - send 'continue' to go on.")
        else:
            reply, ok = friendly_error_message(result.reply_text or "Task failed."), False
            self.report({'ERROR'}, reply.splitlines()[0][:200])
        _set_reply(context.scene, reply, ok)
        return self._finish(context, reply, ok)

    def _finish_with_error(self, context, payload):
        from ..reliability.friendly_errors import friendly_error_message, is_quota_error

        message = friendly_error_message(payload)
        if not is_quota_error(payload):
            message = f"Unexpected error: {message}"
        _set_reply(context.scene, message, False)
        self.report({'ERROR'}, message.splitlines()[0][:200])
        return self._finish(context, message, False)

    def _finish(self, context, reply: str = "", ok: bool = True, stopped: bool = False):
        _run_finished()
        try:
            _remember_run(getattr(context.scene, "aiagent_last_prompt", ""), reply, ok)
        except Exception:  # noqa: BLE001
            pass
        try:
            from .. import get_tool_caller
            from ..copilot.approval import get_gate
            get_gate().answer(False)
            get_tool_caller().approver = None
        except Exception:  # noqa: BLE001
            pass
        try:
            context.window_manager.event_timer_remove(self._timer)
        except Exception:  # noqa: BLE001
            pass
        try:
            from ..copilot.activity import clear, end_run
            clear()
            end_run()                 # (the 'abandon' mark stays until the next Generate)
        except Exception:  # noqa: BLE001
            pass
        context.scene.aiagent_is_running = False
        context.scene.aiagent_status_text = ""
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_inspect_scene(bpy.types.Operator):

    bl_idname = "aiagent.inspect_scene"
    bl_label = "Inspect Scene"

    def execute(self, context):
        import json
        from .. import get_registry

        result = get_registry().get("scene.inspect").execute()
        if result.success:
            print(json.dumps(result.data, indent=2))
            self.report({'INFO'}, "Scene printed to the System Console.")
        else:
            self.report({'ERROR'}, f"Scene inspect failed: {result.error}")
        return {'FINISHED'}


class AIAGENT_OT_run_inspection(bpy.types.Operator):
    """Check the scene geometry (normals, topology, overlaps) and fix what can be fixed"""

    bl_idname = "aiagent.run_inspection"
    bl_label = "Run Scene Check"

    def execute(self, context):
        from .. import get_bridge
        from ..qa.inspection_loop import InspectionLoop

        report = InspectionLoop(get_bridge()).run()
        context.scene.aiagent_qa_passed = report.passed
        context.scene.aiagent_qa_retries = report.retries_used

        if report.passed:
            context.scene.aiagent_qa_report_text = ""
            self.report({'INFO'}, "Scene check passed — no issues found.")
        else:
            lines = [f"[{issue.severity.value.upper()}] {issue.object_name}: {issue.message}" for issue in report.issues]
            context.scene.aiagent_qa_report_text = "\n".join(lines)
            self.report({'WARNING'}, f"Scene check found {len(report.issues)} issue(s).")
        return {'FINISHED'}


# ============================================================================= panels
# ============================================================================= recent tasks / revert / quick actions
_RECENT = {"tasks": None}


def recent_tasks():
    from . import run_state
    if _RECENT["tasks"] is None:
        _RECENT["tasks"] = run_state.load_recent()
    return _RECENT["tasks"]


def _remember_run(prompt: str, reply: str, ok: bool) -> None:
    from . import run_state
    controller = _controller_or_none()
    log = getattr(controller, "last_log_path", "") or ""
    _RECENT["tasks"] = run_state.add_task(recent_tasks(), prompt, reply, ok, _RUN.get("seconds"), log)
    run_state.save_recent(_RECENT["tasks"])


def _selected_names(context):
    try:
        return [o.name for o in context.selected_objects]
    except Exception:  # noqa: BLE001
        return []


class AIAGENT_OT_use_recent(bpy.types.Operator):
    """Put this earlier prompt back in the prompt box"""

    bl_idname = "aiagent.use_recent"
    bl_label = "Use Prompt"
    bl_options = {'INTERNAL'}

    index: _prop("IntProperty", default=0, options={'SKIP_SAVE'})

    def execute(self, context):
        tasks = recent_tasks()
        if not 0 <= self.index < len(tasks):
            return {'CANCELLED'}
        set_prompt(context.scene, tasks[self.index]["prompt"])
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_retry(bpy.types.Operator):
    """Run this prompt again"""

    bl_idname = "aiagent.retry"
    bl_label = "Retry"
    bl_options = {'INTERNAL'}

    index: _prop("IntProperty", default=0, options={'SKIP_SAVE'})

    def execute(self, context):
        tasks = recent_tasks()
        if context.scene.aiagent_is_running or not 0 <= self.index < len(tasks):
            return {'CANCELLED'}
        set_prompt(context.scene, tasks[self.index]["prompt"])
        try:
            return bpy.ops.aiagent.copilot_submit()
        except Exception as exc:  # noqa: BLE001
            self.report({'WARNING'}, f"Prompt restored - press Generate ({exc}).")
            return {'FINISHED'}


class AIAGENT_OT_view_log(bpy.types.Operator):
    """Open the report of this run: what happened, every step and tool, all errors and where the time went"""

    bl_idname = "aiagent.view_log"
    bl_label = "View Logs"
    bl_options = {'INTERNAL'}

    index: _prop("IntProperty", default=0, options={'SKIP_SAVE'})

    def execute(self, context):
        tasks = recent_tasks()
        path = tasks[self.index].get("log", "") if 0 <= self.index < len(tasks) else ""
        if self.index < 0:                                   # the live trace of the run going on now
            from ..observability.run_trace import live_path
            path = live_path()
        elif path.endswith(".json") and os.path.isfile(path[:-5] + "_report.txt"):
            path = path[:-5] + "_report.txt"                 # the readable report first
        if not path or not os.path.isfile(path):
            folder = os.environ.get("BLENDER_AI_LOG_DIR") or os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "logs")
            if not os.path.isdir(folder):
                self.report({'WARNING'}, "No log yet.")
                return {'CANCELLED'}
            path = folder
        try:
            bpy.ops.wm.path_open(filepath=path)
        except Exception as exc:  # noqa: BLE001
            self.report({'WARNING'}, f"Log: {path} ({exc})")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Opened {path}")
        return {'FINISHED'}


class AIAGENT_OT_revert(bpy.types.Operator):
    """Undo everything the last AI run changed: the scene goes back to how it was before you pressed Generate"""

    bl_idname = "aiagent.revert"
    bl_label = "Revert AI Changes"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        from . import run_state
        return run_state.has_checkpoint() and not context.scene.aiagent_is_running

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        from . import run_state
        from .. import get_bridge
        message = run_state.revert(get_bridge())
        self.report({'INFO'} if message.startswith("Reverted") else {'WARNING'}, message)
        _set_reply(context.scene, message, message.startswith("Reverted"))
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_quick_prompt(bpy.types.Operator):
    """Fill the prompt with a ready request for the selected objects (edit it, then press Generate)"""

    bl_idname = "aiagent.quick_prompt"
    bl_label = "Quick Prompt"
    bl_options = {'INTERNAL'}

    kind: _prop("EnumProperty", items=[('MODELING', "Modeling", ""), ('MATERIAL', "Material", ""),
                                       ('LIGHTING', "Lighting", "")], default='MATERIAL', options={'SKIP_SAVE'})

    def execute(self, context):
        from . import run_state
        set_prompt(context.scene, run_state.quick_prompt(self.kind, _selected_names(context)))
        _redraw(context)
        return {'FINISHED'}


class AIAGENT_OT_copilot_continue(bpy.types.Operator):
    """Continue the last stopped / failed run from where it is - with the provider picked now (the scene keeps
    what was built; only what is missing is built)"""

    bl_idname = "aiagent.copilot_continue"
    bl_label = "Continue"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        from ..copilot import resume
        text = resume.prompt()
        if not text:
            self.report({'INFO'}, "Nothing to continue.")
            return {'CANCELLED'}
        set_prompt(context.scene, text)
        return bpy.ops.aiagent.copilot_submit()


class AIAGENT_OT_open_prefs(bpy.types.Operator):
    """Open the add-on preferences (API keys)"""

    bl_idname = "aiagent.open_prefs"
    bl_label = "API Keys"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        try:
            bpy.ops.screen.userpref_show()
            context.preferences.active_section = 'ADDONS'
            context.window_manager.addon_search = "AI Agent"
        except Exception:  # noqa: BLE001
            pass
        return {'FINISHED'}


class AIAgentPanel(bpy.types.Panel):
    """AI Copilot — sidebar panel"""

    bl_label = "AI Copilot"
    bl_idname = "AIAGENT_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "AI Agent"

    def draw_header(self, context):
        self.layout.label(text="", icon=_icon('LIGHT_SUN'))

    def draw(self, context):
        _safe_draw(self, context, self._draw_body)

    def _draw_body(self, context):
        layout = self.layout
        scene = context.scene
        running = scene.aiagent_is_running
        width = _chars_per_line(context)
        controller = _controller_or_none()
        provider = getattr(controller, "current_provider_name", "mock") if controller is not None else "mock"
        selected = scene.aiagent_provider_choice
        info = PROVIDERS.get(selected)

        if getattr(bpy, "props", None) is not None and not hasattr(bpy.types, "AIAGENT_OT_prompt_paste"):
            warn = layout.box()
            warn.alert = True
            warn.label(text="Add-on files are out of date.", icon=_icon('ERROR'))
            _draw_wrapped(warn, "Remove the add-on, install the full blender_ai_agent.zip again, then restart Blender.",
                          width - 2)

        # ---- header: title, status, model
        head = layout.column(align=True)
        title = head.row(align=True)
        title.label(text="Blender AI Copilot", icon=_icon('OUTLINER_OB_LIGHT'))
        if hasattr(scene, "aiagent_show_settings"):
            title.prop(scene, "aiagent_show_settings", text="", icon=_icon('PREFERENCES'), emboss=False)
        sub = head.row()
        sub.scale_y = 0.75
        sub.enabled = False
        sub.label(text="Intelligent 3D Assistant")

        status = layout.row(align=True)
        key_ok = _has_key(selected)
        if running:
            status.label(text="Working", icon=_icon('TIME'))
        elif not key_ok:
            status.alert = True
            status.label(text="No API key", icon=_icon('ERROR'))
        elif provider == "mock":
            status.alert = True
            status.label(text="Not connected", icon=_icon('ERROR'))
        else:
            status.label(text="Ready", icon=_icon('CHECKMARK'))
        pick = status.row(align=True)
        pick.enabled = not running
        pick.prop(scene, "aiagent_provider_choice", text="")       # Gemini / Claude / OpenAI, always visible
        if info is not None and key_ok:
            pick.prop(scene, info[2], text="")
        used = _today_usage(selected, _selected_model(scene, selected) if key_ok else "")
        if used:
            line = layout.row()
            line.scale_y = 0.75
            line.enabled = False
            line.label(text=used[:110], icon=_icon('SORTTIME'))
        if SWITCH_NOTE["text"]:
            note = layout.row()
            note.scale_y = 0.8
            note.alert = SWITCH_NOTE["error"]
            note.label(text=SWITCH_NOTE["text"][:120], icon=_icon('ERROR' if SWITCH_NOTE["error"] else 'LINKED'))

        # ---- connection / settings (always shown while no key is set)
        # (no key yet: only the key box + Submit, right here - no settings to open; the provider / model are picked
        # in the row above)
        if getattr(scene, "aiagent_show_settings", False) or getattr(scene, "aiagent_change_key", False) \
                or not key_ok or provider == "mock":
            compact = not getattr(scene, "aiagent_show_settings", False)
            self._draw_settings(layout, context, scene, selected, info, provider, running, width, compact=compact)

        # ---- scene context
        ctx = layout.box()
        row = ctx.row(align=True)
        row.label(text="Scene Context", icon=_icon('SCENE_DATA'))
        if hasattr(scene, "aiagent_scene_context"):
            row.prop(scene, "aiagent_scene_context", text="Auto", toggle=True)
        names = _selected_names(context)
        line = ctx.row()
        line.scale_y = 0.8
        line.enabled = False
        if getattr(scene, "aiagent_scene_context", True):
            line.label(text=(f"{len(names)} selected object(s) + scene info" if names else "Whole scene info"),
                       icon=_icon('OBJECT_DATA'))
        else:
            line.label(text="Off - only the prompt is sent", icon=_icon('OBJECT_DATA'))

        # ---- prompt
        layout.label(text="AI Prompt", icon=_icon('TEXT'))
        _draw_prompt_box(layout, scene, width)
        text = prompt_text(scene)

        action = layout.row()
        action.scale_y = 1.9
        if running:
            action.alert = True
            _op(action, "aiagent.copilot_stop", text="Stop", icon=_icon('CANCEL'))
        elif worker_alive():                       # a run started earlier is still going in the background
            action.alert = True
            _op(action, "aiagent.copilot_stop", text="Stop previous run", icon=_icon('CANCEL'))
            note = layout.row()
            note.scale_y = 0.8
            note.label(text="A previous run is still finishing - wait or stop it.", icon=_icon('INFO'))
        else:
            selected_now = getattr(scene, "aiagent_provider_choice", "") or ""
            if selected_now and not _has_key(selected_now):
                warn = layout.row()
                warn.alert = True
                label = PROVIDERS.get(selected_now, (selected_now,))[0]
                warn.label(text=f"No {label} API key added - paste it above and press Submit Key",
                           icon=_icon('ERROR'))
            action.enabled = bool(text.strip())
            _op(action, "aiagent.copilot_submit", text="Generate with AI", icon=_icon('SHADERFX'))

        if running:
            self._draw_live(layout, width)
        else:
            self._draw_result(layout, scene, width)
            if not worker_alive():
                self._draw_continue(layout, scene, width)

        # ---- recent tasks
        self._draw_recent(layout, scene, width, running)

        # ---- quick actions
        quick = layout.row(align=True)
        quick.enabled = not running
        from .run_state import QUICK_ACTIONS
        for kind, (label, icon, _template) in QUICK_ACTIONS.items():
            _set_op_prop(_op(quick, "aiagent.quick_prompt", text=label, icon=_icon(icon)), 'kind', kind)

    # ------------------------------------------------------------------ sections
    def _draw_settings(self, layout, context, scene, selected, info, provider, running, width, compact=False):
        box = layout.box()
        if not compact:
            col = box.column(align=True)
            col.enabled = not running
            col.use_property_split = True
            col.use_property_decorate = False
            col.prop(scene, "aiagent_provider_choice", text="Provider")
            if info is not None:
                col.prop(scene, info[2], text="Model")
        prefs = None
        try:
            from ..prefs import PROVIDER_KEY, get_prefs
            prefs = get_prefs(context)
            entry = PROVIDER_KEY.get(selected)
        except Exception:  # noqa: BLE001
            entry = None
        has_key = _has_key(selected)
        changing = bool(getattr(scene, "aiagent_change_key", False))
        if entry is not None and (not has_key or changing) and hasattr(scene, "aiagent_key_input"):
            prop, env, label, url = entry
            need = box.column(align=True)
            need.enabled = not running
            title = need.row()
            title.alert = not has_key
            title.label(text=f"{label} API key {'needed' if not has_key else '- paste a new one'}", icon=_icon('KEYINGSET'))
            keyrow = need.row(align=True)
            keyrow.prop(scene, "aiagent_key_input", text="")
            op = keyrow.operator("wm.url_open", text="Get key", icon=_icon('URL'))
            op.url = url
            submit = need.row(align=True)
            submit.scale_y = 1.4
            _op(submit, "aiagent.save_key", text="Submit Key", icon=_icon('CHECKMARK'))
            if changing:
                submit.prop(scene, "aiagent_change_key", text="Cancel", toggle=True, icon=_icon('X'))
            hint = box.column(align=True)
            hint.scale_y = 0.8
            free = "free key" if selected == "gemini" else "paid key"
            _draw_wrapped(hint, f"{label} needs a {free}: click Get key, copy it, paste it above and press Submit Key. "
                                "It is saved in Blender's preferences on this computer, never in your .blend file.",
                          width - 2, icon='INFO')
        elif entry is not None and has_key:
            prop, env, label, url = entry
            saved = box.row(align=True)
            saved.label(text=f"{label} key saved", icon=_icon('CHECKMARK'))
            if hasattr(scene, "aiagent_change_key"):
                saved.prop(scene, "aiagent_change_key", text="Change", toggle=True)
        elif info is not None and not has_key:
            missing = box.row()
            missing.alert = True
            missing.label(text=f"{info[1]} not set", icon=_icon('ERROR'))

    def _draw_live(self, layout, width):
        box = layout.box()
        box.label(text=_working_text(), icon=_icon('TIME'))
        try:
            from ..copilot import activity
            from ..copilot.step_progress import get_tracker
            now = activity.get_text()
            check = activity.get_check()
            steps = get_tracker().snapshot().steps
        except Exception:  # noqa: BLE001
            now, check, steps = "", "", []
        if steps:
            col = box.column(align=True)
            col.scale_y = 0.85
            icons = {"done": 'CHECKMARK', "running": 'PLAY', "failed": 'ERROR', "skipped": 'X'}
            for number, step in enumerate(steps, 1):
                label = str(step.get("label", ""))
                short = label if len(label) <= width - 8 else label[: width - 9] + "…"
                col.label(text=f"{number}. {short}", icon=_icon(icons.get(step.get("status"), 'BLANK1')))
        plan = getattr(_controller_or_none(), "plan_text", "") or ""
        if plan:
            # what will be built - written by the AI BEFORE building (checklist with counts and places)
            plan_box = box.box()
            plan_box.label(text="Plan (written before building)", icon=_icon('CHECKBOX_HLT'))
            col = plan_box.column(align=True)
            col.scale_y = 0.8
            shown = 0
            for line in plan.splitlines():
                _draw_wrapped(col, line, width - 4, max_lines=2)
                shown += 1
                if shown >= 12:
                    break
        if now:
            _draw_wrapped(box, now, width - 2, max_lines=2, icon='TOOL_SETTINGS')
        if check:
            _draw_wrapped(box, check, width - 2, max_lines=2, icon='HIDE_OFF')
        # what is running right now, step by step (also readable if Blender seems stuck)
        live = box.row(align=True)
        _set_op_prop(_op(live, "aiagent.view_log", text="Open Live Trace", icon=_icon('TEXT')), 'index', -1)
        _op(live, "aiagent.open_checks", text="Check Images", icon=_icon('IMAGE_DATA'))
        _op(live, "aiagent.find_errors", text="Find Errors", icon=_icon('ERROR'))

    def _draw_continue(self, layout, scene, width):
        """After a stopped / failed run: continue it from where it is - with the provider picked now."""
        try:
            from ..copilot import resume
            info = resume.pending()
        except Exception:  # noqa: BLE001
            info = None
        if not info:
            return
        box = layout.box()
        selected = getattr(scene, "aiagent_provider_choice", "") or ""
        label = PROVIDERS.get(selected, (selected,))[0]
        _draw_wrapped(box, f"Unfinished ({info.get('why', 'stopped')}): {info.get('request', '')}", width - 2,
                      max_lines=2, icon='INFO')
        row = box.row()
        row.scale_y = 1.3
        row.enabled = _has_key(selected)
        _op(row, "aiagent.copilot_continue", text=f"Continue with {label}", icon=_icon('PLAY'))
        if not _has_key(selected):
            box.label(text=f"No {label} API key added - add it above first", icon=_icon('ERROR'))

    def _draw_result(self, layout, scene, width):
        reply = getattr(scene, "aiagent_last_reply", "")
        if not reply:
            return
        from .run_state import STATUS_ICON, STATUS_WORD, check_line, classify
        state = classify(reply, getattr(scene, "aiagent_last_reply_ok", True))
        box = layout.box()
        if state == "failed":
            box.alert = True
        box.label(text=_finished_text(STATUS_WORD[state]), icon=_icon(STATUS_ICON[state]))
        check = check_line(reply)
        if check:
            box.label(text=check, icon=_icon('HIDE_OFF'))
        if state == "partial":
            for line in [l for l in reply.splitlines() if l.startswith("✗")][:2]:
                _draw_wrapped(box, line.replace("✗", "Not done:", 1), width - 2, max_lines=3)
        elif state == "failed":
            _draw_wrapped(box, reply.strip().splitlines()[0], width - 2, max_lines=3)
        problems = [l.strip()[2:] for l in reply.splitlines() if l.strip().startswith("- ")][:3]
        if problems and state != "completed" or (problems and "problems remain" in reply):
            col = box.column(align=True)
            col.scale_y = 0.8
            for problem in problems:
                _draw_wrapped(col, problem, width - 2, max_lines=2, icon='DOT')

    def _draw_recent(self, layout, scene, width, running):
        from .run_state import STATUS_ICON, STATUS_WORD, has_checkpoint, title
        tasks = recent_tasks()
        header = layout.row(align=True)
        if hasattr(scene, "aiagent_show_history"):
            header.prop(scene, "aiagent_show_history", text="Recent Tasks", emboss=False,
                        icon=_icon('DISCLOSURE_TRI_DOWN' if scene.aiagent_show_history else 'DISCLOSURE_TRI_RIGHT'))
        else:
            header.label(text="Recent Tasks")
        if not getattr(scene, "aiagent_show_history", True):
            return
        if not tasks:
            empty = layout.row()
            empty.enabled = False
            empty.label(text="No tasks yet", icon=_icon('TIME'))
            return
        latest = tasks[0]
        card = layout.box()
        card.label(text=title(latest["prompt"], max(16, width - 6)), icon=_icon('OUTLINER_OB_LIGHT'))
        try:
            from ..copilot.step_progress import format_duration
            took = f" in {format_duration(latest['seconds'])}" if latest.get("seconds") is not None else ""
        except Exception:  # noqa: BLE001
            took = ""
        state = latest.get("status", "completed")
        row = card.row()
        row.scale_y = 0.85
        row.label(text=f"{STATUS_WORD.get(state, state)}{took}", icon=_icon(STATUS_ICON.get(state, 'INFO')))
        if latest.get("check"):
            row = card.row()
            row.scale_y = 0.85
            row.label(text=latest["check"], icon=_icon('HIDE_OFF'))
        buttons = card.row(align=True)
        buttons.enabled = not running
        _set_op_prop(_op(buttons, "aiagent.view_log", text="View Report", icon=_icon('TEXT')), 'index', 0)
        _op(buttons, "aiagent.open_checks", text="Check Images", icon=_icon('IMAGE_DATA'))
        _op(buttons, "aiagent.find_errors", text="Find Errors", icon=_icon('ERROR'))
        _set_op_prop(_op(buttons, "aiagent.retry", text="Retry", icon=_icon('FILE_REFRESH')), 'index', 0)
        revert = card.row()
        revert.enabled = not running and has_checkpoint()
        _op(revert, "aiagent.revert", text="Revert AI Changes", icon=_icon('LOOP_BACK'))
        older = tasks[1:5]
        if older:
            col = layout.column(align=True)
            for index, task in enumerate(older, 1):
                item = col.row(align=True)
                item.enabled = not running
                op = _op(item, "aiagent.use_recent", text=title(task["prompt"], max(14, width - 8)),
                         icon=_icon(STATUS_ICON.get(task.get("status"), 'INFO')), emboss=False)
                _set_op_prop(op, 'index', index)


class AIAGENT_PT_scene_check(bpy.types.Panel):
    bl_label = "Scene Check"
    bl_idname = "AIAGENT_PT_scene_check"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "AI Agent"
    bl_parent_id = "AIAGENT_PT_panel"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.label(text="", icon=_icon('VIEWZOOM'))

    def draw(self, context):
        _safe_draw(self, context, self._draw_body)

    def _draw_body(self, context):
        layout = self.layout
        scene = context.scene
        width = _chars_per_line(context)

        row = layout.row()
        row.scale_y = 1.2
        row.enabled = not scene.aiagent_is_running
        _op(row, "aiagent.run_inspection", text="Check Geometry", icon=_icon('VIEWZOOM'))

        report_text = getattr(scene, "aiagent_qa_report_text", "")
        if report_text or scene.aiagent_qa_passed:
            box = layout.box()
            if scene.aiagent_qa_passed:
                box.label(text="Passed — no issues found", icon=_icon('CHECKMARK'))
            else:
                box.alert = True
                box.label(text=f"Issues found ({scene.aiagent_qa_retries} fix round(s))", icon=_icon('ERROR'))
                for line in report_text.split("\n"):
                    if line:
                        _draw_wrapped(box, line, width - 2)
