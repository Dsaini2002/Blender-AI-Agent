"""API keys stored in the add-on preferences, so a new user only pastes a key - no environment variables.

Keys typed here are copied into the environment (GEMINI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY) because every
part of the add-on (agent, vision check, build loop) reads them from there. A key set outside Blender in the
environment still works and is never overwritten by an empty field.
"""

import os

import bpy

ADDON = __package__ or "blender_ai_agent"

# (preferences property, environment variable, label, where to get a key)
KEYS = (
    ("gemini_api_key", "GEMINI_API_KEY", "Google Gemini", "https://aistudio.google.com/apikey"),
    ("openai_api_key", "OPENAI_API_KEY", "OpenAI", "https://platform.openai.com/api-keys"),
    ("claude_api_key", "ANTHROPIC_API_KEY", "Anthropic Claude", "https://console.anthropic.com/settings/keys"),
)
PROVIDER_KEY = {"gemini": KEYS[0], "openai": KEYS[1], "claude": KEYS[2]}

_applied = {}          # environment variable -> value we put there (so clearing the field can take it back)


# Removing the add-on (to install a new version) deletes its preferences - and the keys with them. A copy of each
# key is kept in ~/BlenderAIAgent/keys.json (only on this computer, readable only by this user), so a key is asked
# for ONCE and a new version finds it again.
def keys_file() -> str:
    if os.environ.get("BLENDER_AI_KEYS_FILE"):
        return os.environ["BLENDER_AI_KEYS_FILE"]
    return os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "keys.json")


def _read_key_file() -> dict:
    try:
        import json
        with open(keys_file(), encoding="utf-8") as handle:
            data = json.load(handle)
        return {k: v for k, v in data.items() if isinstance(v, str) and v.strip()} if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_key_file(data: dict) -> None:
    try:
        import json
        path = keys_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=1)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        pass


def remember_key(env: str, value: str) -> None:
    data = _read_key_file()
    value = (value or "").strip()
    if value and data.get(env) != value:
        data[env] = value
        _write_key_file(data)
    elif not value and env in data:
        data.pop(env)
        _write_key_file(data)


def load_remembered_keys() -> None:
    """Keys saved by an earlier install -> environment (never over a key that is already set)."""
    for env, value in _read_key_file().items():
        if env in {k[1] for k in KEYS} and not os.environ.get(env, "").strip():
            os.environ[env] = value


def get_prefs(context=None):
    try:
        context = context or bpy.context
        return context.preferences.addons[ADDON].preferences
    except (AttributeError, KeyError):
        return None


def apply_keys(prefs=None) -> None:
    prefs = prefs if prefs is not None else get_prefs()
    if prefs is None:
        load_remembered_keys()
        return
    for prop, env, _label, _url in KEYS:
        value = (getattr(prefs, prop, "") or "").strip()
        if value:
            os.environ[env] = value
            _applied[env] = value
            remember_key(env, value)
        elif env in _applied and os.environ.get(env) == _applied[env]:
            os.environ.pop(env, None)            # the user cleared a key they had typed here
            _applied.pop(env, None)
            remember_key(env, "")
    load_remembered_keys()


def has_key(provider: str) -> bool:
    entry = PROVIDER_KEY.get(provider)
    return bool(entry and os.environ.get(entry[1], "").strip())


def _save_preferences_soon() -> None:
    def _save():
        try:
            bpy.ops.wm.save_userpref()
        except Exception:  # noqa: BLE001 — saving is a convenience; Blender also saves on quit
            pass
        return None
    try:
        bpy.app.timers.register(_save, first_interval=0.5)
    except Exception:  # noqa: BLE001
        pass


def _on_key_changed(self, context):
    apply_keys(self)
    try:
        from . import reset_providers
        reset_providers()
    except Exception:  # noqa: BLE001
        pass
    _save_preferences_soon()


def _key_prop(**kwargs):
    props = getattr(bpy, "props", None)
    return props.StringProperty(subtype='PASSWORD', default="", update=_on_key_changed, **kwargs) if props else None


_PreferencesBase = getattr(getattr(bpy, "types", None), "AddonPreferences", object)


class AIAgentPreferences(_PreferencesBase):
    bl_idname = ADDON

    gemini_api_key: _key_prop(name="Gemini API key",
                              description="Free key from Google AI Studio (aistudio.google.com/apikey)")
    openai_api_key: _key_prop(name="OpenAI API key", description="Paid key from platform.openai.com/api-keys")
    claude_api_key: _key_prop(name="Claude API key",
                              description="Anthropic key from console.anthropic.com/settings/keys (paid)")

    def draw(self, context):
        layout = self.layout
        layout.label(text="Paste one API key (Gemini, OpenAI or Claude) and press Enter. It is saved on this computer.",
                     icon='INFO')
        remembered = _read_key_file()
        for prop, env, label, url in KEYS:
            row = layout.row(align=True)
            row.prop(self, prop)
            op = row.operator("wm.url_open", text="Get key", icon='URL')
            op.url = url
            if getattr(self, prop):
                layout.label(text=f"{label} key saved - ready to use.", icon='CHECKMARK')
            elif remembered.get(env):
                layout.label(text=f"{label} key saved from before - ready to use (paste a new one to change it).",
                             icon='CHECKMARK')
            elif os.environ.get(env):
                layout.label(text=f"{label}: using {env} from the environment.", icon='CHECKMARK')
