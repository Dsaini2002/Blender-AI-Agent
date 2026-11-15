
import base64
import json
import math
import os
import re
import socket
import time
import urllib.error
import urllib.request
from .. import net as _net
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .build_script import RunResult, ScriptError, ScriptLimits, function_name, run_script, validate_script


class BuilderError(Exception):
    def __init__(self, message: str, user_message: Optional[str] = None):
        super().__init__(message)
        self.user_message = user_message or message


# =============================================================================
# Config
# =============================================================================
@dataclass
class BuilderConfig:
    api_key: str = ""
    api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    model: str = ""
    fallback_model: str = ""
    max_iterations: int = 3
    target_score: float = 8.0
    views: Tuple[str, ...] = ("front", "right", "top", "three_quarter")
    resolution: int = 512
    request_timeout_s: float = 120.0
    max_script_retries: int = 2
    max_seconds: float = 1200.0
    output_dir: str = ""
    vision_provider: str = ""          # "gemini" / "claude"; empty = the AI picked in the panel, else Gemini
    vision_model: str = ""


def builder_config_path() -> str:
    env = os.environ.get("BLENDER_AI_BUILDER_CONFIG")
    return os.path.expanduser(env) if env else os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "builder.json")


def load_builder_config(path: Optional[str] = None) -> BuilderConfig:
    cfg = BuilderConfig()
    try:
        with open(path or builder_config_path(), "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            for key, value in data.items():
                if hasattr(cfg, key):
                    if key == "views" and isinstance(value, list):
                        value = tuple(str(v) for v in value)
                    setattr(cfg, key, value)
    except (OSError, ValueError):
        pass
    gemini_key = os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")
    claude_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    # The AI that LOOKS at the renders is the AI picked in the panel (same provider, same model) - never another one.
    active = os.environ.get("BLENDER_AI_ACTIVE_PROVIDER", "")
    active_model = os.environ.get("BLENDER_AI_ACTIVE_MODEL", "")
    wanted = (cfg.vision_provider or os.environ.get("BLENDER_AI_VISION", "") or
              (active if active in ("gemini", "claude", "openai") else "")).strip().lower()
    if not wanted:
        wanted = "gemini" if gemini_key else "claude" if claude_key else "openai" if openai_key else "gemini"
    cfg.vision_provider = wanted if wanted in ("gemini", "claude", "openai") else "gemini"
    if cfg.vision_provider == "claude":
        cfg.api_key = claude_key or cfg.api_key
        cfg.vision_model = cfg.vision_model or (active_model if active == "claude" else "")
    elif cfg.vision_provider == "openai":
        cfg.api_key = openai_key or cfg.api_key
        cfg.vision_model = cfg.vision_model or (active_model if active == "openai" else "")
    cfg.api_key = cfg.api_key or gemini_key
    cfg.model = cfg.model or os.environ.get("BUILDER_MODEL", "") or \
        (active_model if cfg.vision_provider == "gemini" and active == "gemini" else "")
    try:
        cfg.max_iterations = max(1, min(6, int(cfg.max_iterations)))
        cfg.target_score = max(1.0, min(10.0, float(cfg.target_score)))
        cfg.resolution = max(128, min(1024, int(cfg.resolution)))
        cfg.request_timeout_s = max(5.0, float(cfg.request_timeout_s))
    except (TypeError, ValueError):
        cfg = BuilderConfig(api_key=cfg.api_key)
    return cfg


def make_vision_client(cfg: "BuilderConfig"):
    """The client that looks at renders: Claude when the config says so, otherwise Gemini."""
    if getattr(cfg, "vision_provider", "") == "claude":
        from ..providers.claude_provider import ClaudeVisionClient
        return ClaudeVisionClient(cfg)
    if getattr(cfg, "vision_provider", "") == "openai":
        from ..providers.openai_provider import OpenAIVisionClient
        return OpenAIVisionClient(cfg)
    return GeminiClient(cfg)


# =============================================================================
# Gemini REST client (text + images)
# =============================================================================
class GeminiClient:

    def __init__(self, cfg: BuilderConfig, clock: Callable[[], float] = time.monotonic):
        self.cfg = cfg
        self._models: Optional[List[str]] = None
        self._cooldown: Dict[str, float] = {}
        self._clock = clock

    def _available(self) -> List[str]:
        now = self._clock()
        live = [m for m in self.models() if self._cooldown.get(m, 0.0) <= now]
        return live or self.models()

    def _request(self, url: str, payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Dict[str, Any]]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET",
                                         headers={"x-goog-api-key": self.cfg.api_key, "Content-Type": "application/json"})
        try:
            with _net.urlopen(request, timeout=self.cfg.request_timeout_s) as response:
                body = response.read()
                status = response.status
        except urllib.error.HTTPError as exc:
            body, status = exc.read(), exc.code
        except urllib.error.URLError as exc:
            raise BuilderError(f"cannot reach Gemini: {exc.reason}", f"Could not connect to Gemini ({exc.reason}).") from exc
        except (socket.timeout, TimeoutError) as exc:
            raise BuilderError("timeout", f"Gemini did not answer within {self.cfg.request_timeout_s:.0f}s.") from exc
        except OSError as exc:            # e.g. a broken certificate file set by another add-on
            raise BuilderError(f"connection error: {type(exc).__name__}: {exc}",
                               "Could not open a secure connection to Gemini "
                               f"({type(exc).__name__}: {exc}). Another add-on may have changed Python's SSL "
                               "settings; restart Blender and try again.") from exc
        try:
            parsed = json.loads(body.decode("utf-8", "replace"))
        except ValueError:
            parsed = {}
        return status, parsed if isinstance(parsed, dict) else {}

    def models(self) -> List[str]:
        if self._models is not None:
            return self._models
        configured = [m.replace("models/", "") for m in (self.cfg.model, self.cfg.fallback_model) if m]
        if self.cfg.model and self.cfg.fallback_model:
            self._models = configured
            return self._models
        status, data = self._request(f"{self.cfg.api_base.rstrip('/')}/models?pageSize=200")
        if status != 200:
            message = (data.get("error") or {}).get("message", f"HTTP {status}")
            raise BuilderError(f"list models failed: {message}", f"Could not list Gemini models ({status}): {message}")
        flash = []
        for model in data.get("models", []):
            name = str(model.get("name", "")).replace("models/", "")
            methods = model.get("supportedGenerationMethods") or ["generateContent"]
            if "generateContent" not in methods or "flash" not in name:
                continue
            if any(bad in name for bad in ("image", "tts", "live", "audio", "embedding", "native", "robotics", "computer", "latest", "exp")):
                continue
            match = re.search(r"gemini-(\d+(?:\.\d+)?)", name)
            flash.append((float(match.group(1)) if match else 0.0, "lite" in name, "preview" in name, name))
        if not flash and not configured:
            raise BuilderError("no flash model", "No Gemini flash model is available for this key; set 'model' in builder.json.")
        full = sorted((f for f in flash if not f[1]), key=lambda f: (-f[0], f[2], len(f[3])))
        lite = sorted((f for f in flash if f[1]), key=lambda f: (-f[0], f[2], len(f[3])))
        primary = self.cfg.model.replace("models/", "") or (full[0][3] if full else lite[0][3])
        fallback = self.cfg.fallback_model.replace("models/", "") or next(
            (f[3] for f in lite + full if f[3] != primary), "")
        self._models = [m for m in (primary, fallback) if m]
        return self._models

    def generate(self, system: str, parts: List[Dict[str, Any]], json_mode: bool = False, temperature: float = 0.4,
                 max_output_tokens: int = 16384) -> str:
        if not self.cfg.api_key:
            raise BuilderError("no key", "Gemini API key not found (set the GEMINI_API_KEY environment variable).")
        errors: List[str] = []
        for model in self._available():
            for with_json in ((True, False) if json_mode else (False,)):
                config: Dict[str, Any] = {"temperature": temperature, "maxOutputTokens": max_output_tokens}
                if with_json:
                    config["responseMimeType"] = "application/json"
                payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": [{"role": "user", "parts": parts}],
                           "generationConfig": config}
                try:
                    status, data = self._request(f"{self.cfg.api_base.rstrip('/')}/models/{model}:generateContent", payload)
                except BuilderError as exc:
                    if str(exc) != "timeout":
                        raise
                    errors.append(f"{model}: timeout")           # slow model: try the fallback model instead
                    self._cooldown[model] = self._clock() + 60.0
                    break
                message = (data.get("error") or {}).get("message", "")
                if status == 200:
                    block = (data.get("promptFeedback") or {}).get("blockReason")
                    if block:
                        raise BuilderError(f"blocked {block}", f"Gemini blocked the request ({block}). Try rephrasing the prompt.")
                    text = "".join(part.get("text", "") for cand in data.get("candidates", [])[:1]
                                   for part in (cand.get("content") or {}).get("parts", []))
                    try:
                        from ..observability import token_meter
                        meta = data.get("usageMetadata") or {}
                        token_meter.record("gemini", model, meta.get("promptTokenCount", 0),
                                           meta.get("candidatesTokenCount", 0))
                    except Exception:  # noqa: BLE001
                        pass
                    if text.strip():
                        return text
                    errors.append(f"{model}: empty reply")
                    break
                if status == 400 and with_json and "mime" in message.lower():
                    continue
                if status in (429, 500, 503):
                    errors.append(f"{model}: {status}")
                    self._cooldown[model] = self._clock() + (120.0 if status == 429 else 20.0)
                    break
                raise BuilderError(f"gemini {status}: {message}", f"Gemini returned an error ({status}): {message[:200]}")
        quota = any(" 429" in e for e in errors)
        raise BuilderError("; ".join(errors), "Gemini quota is used up (429). Try again in a little while." if quota
                           else "Gemini did not answer: " + "; ".join(errors))


def image_part(path: str) -> Dict[str, Any]:
    with open(path, "rb") as handle:
        raw = handle.read()
    mime = "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg" if raw[:3] == b"\xff\xd8\xff" else "image/webp" \
        if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP" else None
    if mime is None:
        raise BuilderError("bad image", f"This image is not a PNG/JPG/WEBP file: {path}")
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode("ascii")}}


# =============================================================================
# Prompts
# =============================================================================
EXCLUDED_TOOLS = {"python.execute", "render.preview", "vision.observe", "asset.import_model", "asset.list_blend_objects",
                  "asset.import_blend", "template.build", "build.iterate", "build.assess", "model.generate", "model.from_image",
                  "image.generate", "scene.inspect", "mesh.help", "camera.create", "camera.set", "render.setup"}

WRITER_SYSTEM = """You write BUILD SCRIPTS that make a 3D object in Blender. A script is a small Python subset that can ONLY call the tool functions listed below.

LANGUAGE
- Allowed: assignments, for loops over range()/lists, if/elif/else, def functions, list/dict literals, f-strings, list comprehensions, indexing/slicing, math (sin cos tan atan2 sqrt pi radians degrees floor ceil clamp lerp rand), abs min max round sum len int float str list dict tuple sorted zip enumerate any all, note("short comment").
- NOT allowed: import, attribute access (x.y), method calls (s.format), while, lambda, class, try, with, open/eval/exec/print, *args, names starting with _, sets, dict/set comprehensions.
- Call tools ONLY with keyword arguments, e.g. mesh_sdf(name="Body", resolution=60, shapes=[...]). Each call returns a dict: r = mesh_sdf(...); r["name"] is the real object name (Blender may add .001).
- A failing call stops the script and you will be told the line and the reason - so use exact argument names from the list.

RULES FOR THE OBJECT
- Metres, Z up. Build it standing on z=0, centred at the anchor you are given. The FRONT of the object must face -Y (towards Blender's front view).
- Make it RECOGNISABLE: correct proportions, all the parts a real one has (e.g. a car: body, cabin/windows, 4 wheels, lights), parts touching/attached, nothing floating or buried. Use loops for repeated parts (wheels, legs, windows).
- REALISM (every object, any category): (1) three DETAIL LAYERS - big forms, medium parts, then 20-100 small seeded-random pieces (stones, coals, ash, bolts, leaves, scratches) with rand(i, seed) for position/size/rotation, never identical copies; (2) every main surface uses material_recipe (or material_nodes), not a flat colour; (3) anything that glows also gets a light_create of the same colour next to it; (4) add atmosphere where it makes sense (smoke_volume on a big cube, sparks); (5) the ground gets dirt_ground, hard parts a small bevel (modifier_add BEVEL) and shade smooth; (6) nothing floats or sinks.
- MATERIALS: material_recipe(name=..., recipe=..., params={...}, assign_to=[object names]). Recipes: {recipes}. Use material_nodes only to invent something no recipe covers. Glass parts use the glass recipe, tyres rubber, paint car_paint, lamps glow.
- Do NOT create cameras or call render_setup in a build script: the system renders its own views.
- Prefer these builders for organic/round shapes: mesh_sdf (blended solids: bodies, cabins, rocks, animals), mesh_lathe (bottles, wheels' hubs, vases), mesh_prism (flat shapes), character_create (cartoon people), curve_create (tubes, ropes). Use object_create + object_transform for simple boxes and cylinders.
- Do not delete or modify objects that are not yours. Do not render. Keep the script under ~120 lines.

OUTPUT: exactly one ```python code block with the COMPLETE script, nothing else.

TOOLS
{tools}

EXAMPLE 1 (a simple table, centred at the anchor)
```python
cx, cy = 0.0, 0.0
material_create(name="Wood", color=[0.45, 0.28, 0.14])
top = object_create(name="Table_top", primitive="CUBE", location=[cx, cy, 0.75])
object_transform(name=top["name"], scale=[0.8, 0.5, 0.03])
material_assign(object_name=top["name"], material_name="Wood")
for i, (sx, sy) in enumerate([(1, 1), (1, -1), (-1, 1), (-1, -1)]):
    leg = object_create(name=f"Table_leg{i}", primitive="CUBE", location=[cx + 0.7 * sx, cy + 0.4 * sy, 0.36])
    object_transform(name=leg["name"], scale=[0.04, 0.04, 0.36])
    material_assign(object_name=leg["name"], material_name="Wood")
```

EXAMPLE 2 (a simple car: body + solid wheels, front towards -Y, anchor (ax, ay))
```python
ax, ay = 0.0, 0.0
material_recipe(name="Paint", recipe="car_paint", params={"color": [0.55, 0.02, 0.02, 1.0]})
material_recipe(name="Rubber", recipe="rubber")
material_recipe(name="Chrome", recipe="metal_brushed", params={"color": [0.85, 0.85, 0.88, 1.0], "roughness": 0.2})
body = mesh_sdf(name="Car_body", resolution=60, location=[ax, ay, 0], shapes=[
    {"type": "box", "size": [1.8, 4.5, 0.72], "center": [0, 0, 0.62], "rounding": 0.28},
    {"type": "ellipsoid", "radii": [0.83, 1.2, 0.43], "center": [0, 0.2, 1.12], "op": "smooth_union", "k": 0.3}])
material_assign(object_name=body["name"], material_name="Paint")
tyre = [[0.0, -0.11], [0.2, -0.11], [0.25, -0.1], [0.31, -0.11], [0.34, -0.07], [0.345, 0.0], [0.34, 0.07], [0.31, 0.11], [0.25, 0.1], [0.2, 0.11], [0.0, 0.11]]
hub = [[0.0, -0.125], [0.19, -0.125], [0.19, 0.125], [0.0, 0.125]]
for i, (sx, sy) in enumerate([(1, 1), (-1, 1), (1, -1), (-1, -1)]):
    spot = [ax + 0.9 * sx, ay + 1.38 * sy, 0.345]
    t = mesh_lathe(name=f"Car_tyre{i}", profile=tyre, segments=32, location=spot, rotation=[0, 90, 0])
    material_assign(object_name=t["name"], material_name="Rubber")
    h = mesh_lathe(name=f"Car_hub{i}", profile=hub, segments=24, location=spot, rotation=[0, 90, 0])
    material_assign(object_name=h["name"], material_name="Chrome")
```
EXAMPLE 3 (a lit scene - shows the general rules: layers, recipes, light from the emitter, atmosphere, imperfection; centred at the anchor)
```python
cx, cy = 0.0, 0.0
material_recipe(name="Fire_dirt", recipe="dirt_ground")
material_recipe(name="Fire_stone", recipe="rough_stone")
material_recipe(name="Fire_log", recipe="wood_grain")
material_recipe(name="Fire_char", recipe="charred_wood")
material_recipe(name="Fire_ember", recipe="ember")
material_recipe(name="Fire_flame", recipe="fire_flame")
material_recipe(name="Fire_smoke", recipe="smoke_volume")
ground = object_create(name="Fire_ground", primitive="PLANE", location=[cx, cy, 0])
object_transform(name=ground["name"], scale=[6, 6, 1])
material_assign(object_name=ground["name"], material_name="Fire_dirt")
for i in range(14):
    a = 2 * pi * i / 14
    stone = object_create(name=f"Fire_stone{i}", primitive="SPHERE", location=[cx + 1.4 * cos(a), cy + 1.4 * sin(a), 0.12])
    object_transform(name=stone["name"], scale=[0.3 + 0.15 * rand(i, 1), 0.25 + 0.1 * rand(i, 2), 0.2 + 0.08 * rand(i, 3)], rotation=[0.3 * rand(i, 4), 0.3 * rand(i, 5), a])
    material_assign(object_name=stone["name"], material_name="Fire_stone")
for i in range(4):
    a = pi * i / 4 + 0.3
    trunk = object_create(name=f"Fire_log{i}", primitive="CYLINDER", location=[cx, cy, 0.25 + 0.18 * (i % 2)])
    object_transform(name=trunk["name"], scale=[0.2, 0.2, 1.1], rotation=[0, pi / 2, a])
    material_assign(object_name=trunk["name"], material_name="Fire_log" if i % 2 == 0 else "Fire_char")
for i in range(40):
    r = 0.75 * sqrt(rand(i, 11))
    a = 2 * pi * rand(i, 12)
    coal = object_create(name=f"Fire_coal{i}", primitive="SPHERE", location=[cx + r * cos(a), cy + r * sin(a), 0.08 + 0.12 * rand(i, 13)])
    object_transform(name=coal["name"], scale=[0.06 + 0.05 * rand(i, 14), 0.06 + 0.05 * rand(i, 15), 0.04 + 0.03 * rand(i, 16)])
    material_assign(object_name=coal["name"], material_name="Fire_ember")
for k, (h, w) in enumerate([(1.5, 0.38), (1.1, 0.26), (0.8, 0.18)]):
    flame = mesh_sdf(name=f"Fire_flame{k}", resolution=36, location=[cx + 0.08 * k, cy - 0.05 * k, 0.45],
                     shapes=[{"type": "round_cone", "radius": w, "radius_top": 0.0, "height": h}])
    material_assign(object_name=flame["name"], material_name="Fire_flame")
smoke = object_create(name="Fire_smoke", primitive="CUBE", location=[cx, cy, 2.6])
object_transform(name=smoke["name"], scale=[1.0, 1.0, 2.2])
material_assign(object_name=smoke["name"], material_name="Fire_smoke")
light_create(name="Fire_light", light_type="POINT", location=[cx, cy, 0.9], color=[1.0, 0.35, 0.08], energy=900, size=0.6)
light_create(name="Fire_glow", light_type="POINT", location=[cx, cy, 0.15], color=[1.0, 0.1, 0.01], energy=350, size=0.4)
```

WHEELS: always SOLID. Use mesh_lathe with a closed profile [[r, z], ...] that starts and ends on the axis (r = 0) - the lathe axis is Z, so rotation [0, 90, 0] turns it sideways; centre height = wheel radius. NEVER a bare torus or an open ring (it shows holes and the ground through it).
"""

CRITIC_SYSTEM = """You are a strict 3D art reviewer. Judge the attached renders against the REQUEST.
Images, in order: {order}.
Answer with ONLY this JSON object:
{{"score": <number 0-10>, "matches_prompt": <true|false>, "summary": "<one sentence>",
  "problems": [{{"severity": "high|medium|low", "where": "<object or region>", "issue": "<what is wrong, concretely>", "fix": "<what to change in the script>"}}],
  "keep": ["<things that are already right>"]}}
Scoring: 10 = convincing; 7-8 = clearly recognisable, minor flaws; 4-6 = vague resemblance, important parts missing or wrong; 0-3 = wrong or missing.
Check: the object TYPE is exactly what was asked (a sports car is low, wide, with a long sloping hood and a small cabin - NOT a pickup, van or sedan; a horse is not a dog): if the type is wrong, score at most 4. Recognisable silhouette and proportions; every expected part present (a car needs wheels, windows, lights); wheels are SOLID discs (holes or see-through wheels are a high problem); REALISM for any object: at least three detail layers (big forms, medium parts, many small pieces), surfaces with material variation rather than flat colours, glowing things that actually light their surroundings, believable atmosphere (smoke, dust) where it belongs, imperfection (no identical copies, no perfect symmetry) - say exactly which of these is missing; parts attached - not floating, not buried, not badly intersecting; the front faces the camera in the front view; sensible colours/materials; nothing below the ground.
At most 6 problems, most important first. Be specific (say which object and in which direction to move/scale it)."""


def _field_signature(model: Any) -> str:
    import dataclasses
    if model is None or not dataclasses.is_dataclass(model):
        return "..."
    parts = []
    for f in dataclasses.fields(model):
        if f.default is not dataclasses.MISSING:
            default = f.default
        elif f.default_factory is not dataclasses.MISSING:  # type: ignore[misc]
            try:
                default = f.default_factory()  # type: ignore[misc]
            except Exception:  # noqa: BLE001
                default = "..."
        else:
            parts.append(f"{f.name}")
            continue
        shown = repr(default)
        parts.append(f"{f.name}={shown if len(shown) <= 24 else '...'}")
    return ", ".join(parts)


def describe_tools(registry: Any, tool_names: Iterable[str], max_description: int = 260) -> str:
    lines = []
    for name in sorted(tool_names):
        tool = registry.get(name)
        if tool is None:
            continue
        description = " ".join(str(getattr(tool, "description", "")).split())
        if len(description) > max_description:
            cut = description[:max_description]
            description = cut[: cut.rfind(" ")] + " ..."
        lines.append(f"{function_name(name)}({_field_signature(getattr(tool, 'input_model', None))}) - {description}")
    return "\n".join(lines)


def extract_script(text: str) -> str:
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text or "", re.DOTALL | re.IGNORECASE)
    if blocks:
        return max(blocks, key=len).strip()
    return (text or "").strip().strip("`").strip()


@dataclass
class Critique:
    score: float = 0.0
    matches: bool = False
    summary: str = ""
    problems: List[Dict[str, str]] = field(default_factory=list)
    keep: List[str] = field(default_factory=list)
    raw_ok: bool = True
    missing: List[str] = field(default_factory=list)


def parse_critique(text: str, measured: Optional[List[str]] = None) -> Critique:
    candidate = (text or "").strip()
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if match:
        candidate = match.group(0)
    try:
        data = json.loads(candidate)
    except ValueError:
        return Critique(summary="the reviewer's answer could not be read", raw_ok=False)
    if not isinstance(data, dict):
        return Critique(summary="the reviewer's answer could not be read", raw_ok=False)
    try:
        score = max(0.0, min(10.0, float(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0.0
    problems = []
    for item in (data.get("problems") or [])[:10]:
        if isinstance(item, dict):
            problems.append({"severity": str(item.get("severity", "medium")).lower(), "where": str(item.get("where", ""))[:80],
                             "issue": str(item.get("issue", ""))[:300], "fix": str(item.get("fix", ""))[:300]})
        elif isinstance(item, str):
            problems.append({"severity": "medium", "where": "", "issue": item[:300], "fix": ""})
    keep = [str(k)[:120] for k in (data.get("keep") or [])[:8]]
    missing = []
    for item in (data.get("checklist") or [])[:40]:
        if not isinstance(item, dict) or not str(item.get("item", "")).strip():
            continue
        name = str(item["item"])[:120]
        try:
            wanted, seen = int(item.get("wanted", 0) or 0), int(item.get("seen", -1) if item.get("seen") is not None else -1)
        except (TypeError, ValueError):
            wanted, seen = 0, -1
        if item.get("present") is False:
            missing.append(name)
        elif wanted and 0 <= seen < wanted:
            missing.append(f"{name} ({seen} of {wanted} seen - {wanted - seen} more needed)")
        if item.get("where_ok") is False and len(problems) < 14:
            problems.append({"severity": "high", "where": name[:80],
                             "issue": str(item.get("issue") or "not in the right place")[:300],
                             "fix": "move / resize it to where the request and the checklist say"})
    for entry in (data.get("measured") or [])[:30]:
        if not isinstance(entry, dict) or entry.get("real") is not True or not measured:
            continue
        try:
            line = measured[int(entry.get("line", 0)) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        if len(problems) < 16:
            problems.append({"severity": "high", "where": "measured", "issue": line[:300],
                             "fix": "the measured fix in the line"})
    return Critique(score, bool(data.get("matches_prompt", score >= 7)), str(data.get("summary", ""))[:300], problems, keep,
                    missing=missing)


STRICT_REVIEW = """
PRECISION REVIEW - the user wants a 10/10 result, so be exact:
1. Add "checklist": [{"item": "<element>", "present": true|false}] listing EVERY element the request names AND every element
   this kind of scene or object obviously needs (a house: walls, roof, door, windows, steps...; a stadium: pitch, markings,
   goals, stands, lights...). Each missing element is also a HIGH problem.
2. Inspect precisely and report every flaw, small ones too (severity low), up to 10:
   - doors and windows sit flush IN their wall (not floating in front, not sunk inside), door bottoms exactly on the floor,
     real heights (door about 2.1 m, window sill about 0.9 m), centred / aligned on the facade where they should be;
   - repeated items (columns, legs, lamps, posts, seats, stands, windows) have EQUAL heights and sizes, even spacing, and line up;
   - symmetry where the real thing is symmetric; nothing tilted, floating, sunk or cutting through something by mistake;
   - no two objects inside each other: a shelf through a wardrobe, a desk inside a bookshelf, furniture through a wall -
     name both objects in "where";
   - real-world proportions between objects (a person 1.75 m, a chair seat 0.45 m); fitting materials; lighting shows everything.
3. Score 10 ONLY when the checklist is complete and you find no flaw at all; any remaining flaw, even low, means at most 9."""


DEEP_REVIEW = """
DEEP CHECK - you get the scene from EVERY side (front, back, left, right, top, a low eye-level view, two
three-quarter views), ZOOMED OUT (wide: the whole scene and its surroundings) and ZOOMED IN (one close-up per
checklist thing). Use all of them; a thing hidden in one view is visible in another.
1. "checklist": answer EVERY line of the CHECKLIST: {"item": "...", "wanted": <count>, "seen": <count you can see>,
   "present": true|false, "where_ok": true|false, "issue": "<what is wrong with it or its place, '' if nothing>"}.
   seen < wanted means copies are missing. where_ok = it is where the user said (or a sensible place when the user
   said nothing), resting on its support, not inside something, not floating, the right size.
2. "measured": the agent MEASURED the scene; for each MEASURED line say if the images confirm it:
   [{"line": <number>, "real": true|false}]. A measured problem you can see is a HIGH problem.
3. Score 10 only when every checklist line is present with the full count and where_ok, and nothing measured is real."""


def critique_renders(generate: Callable[..., str], request: str, view_paths: List[str], reference: Optional[str] = None,
                     strict: bool = False, note: str = "", checklist: str = "", measured: Optional[List[str]] = None,
                     labels: Optional[Dict[str, str]] = None) -> Critique:
    labels = labels or {}

    def label(path: str) -> str:
        if path in labels:
            return labels[path]
        base = os.path.basename(path)
        if "_cutaway_" in base:
            return "cutaway render (outer walls hidden on purpose)"
        view = base[:-4].split("_", 1)[-1] if "_" in base else base[:-4]
        return f"render view '{view}'"
    order = (["the REFERENCE image the user supplied"] if reference else []) + [label(p) for p in view_paths]
    parts: List[Dict[str, Any]] = [{"text": f"REQUEST: {request}"}]
    if note:
        parts.append({"text": f"NOTE: {note}"})
    if checklist:
        parts.append({"text": "CHECKLIST (what the request asks for - check every line):\n" + checklist})
    if measured:
        parts.append({"text": "MEASURED by the agent in the scene (confirm or reject each with the images):\n" +
                              "\n".join(f"{i}. {line}" for i, line in enumerate(measured, 1))})
    if reference:
        parts.append({"text": "Reference image:"})
        parts.append(image_part(reference))
    for path in view_paths:
        parts.append({"text": label(path)})
        parts.append(image_part(path))
    system = CRITIC_SYSTEM.format(order=", ".join(order))
    if strict:
        system = system.replace("At most 6 problems", "At most 10 problems") + STRICT_REVIEW
    if checklist or measured:
        system += DEEP_REVIEW
    text = generate(system, parts, json_mode=True, temperature=0.2,
                    max_output_tokens=6144 if (checklist or measured) else 4096 if strict else 2048)
    return parse_critique(text, measured)


REVIEW_LOG: List[float] = []

# =============================================================================
# The loop
# =============================================================================
@dataclass
class Iteration:
    number: int
    script: str = ""
    run_ok: bool = False
    run_error: Optional[str] = None
    tool_calls: int = 0
    images: List[str] = field(default_factory=list)
    score: float = 0.0
    summary: str = ""
    problems: List[Dict[str, str]] = field(default_factory=list)
    keep: List[str] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)


@dataclass
class BuildReport:
    success: bool = False
    best_score: float = 0.0
    best_iteration: int = 0
    reached_target: bool = False
    iterations: List[Iteration] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    script: str = ""
    llm_calls: int = 0
    stopped_reason: str = ""
    anchor: List[float] = field(default_factory=list)
    folder: str = ""
    seconds: float = 0.0

    def summary(self) -> Dict[str, Any]:
        return {"success": self.success, "best_score": self.best_score, "best_iteration": self.best_iteration,
                "reached_target": self.reached_target, "stopped_reason": self.stopped_reason, "llm_calls": self.llm_calls,
                "objects": self.objects, "anchor": self.anchor, "folder": self.folder, "seconds": round(self.seconds, 1),
                "iterations": [{"iteration": i.number, "ok": i.run_ok, "error": i.run_error, "score": i.score, "summary": i.summary,
                                "problems": [p["issue"] for p in i.problems[:3]], "tool_calls": i.tool_calls} for i in self.iterations]}


SLOTS = [(0, 0), (4, 0), (-4, 0), (0, 4), (0, -4), (4, 4), (-4, 4), (4, -4), (-4, -4), (8, 0), (-8, 0), (0, 8), (0, -8)]


class SelfCorrectingBuilder:
    def __init__(self, tool_caller: Any, registry: Any, bridge: Any, llm: Any, config: BuilderConfig,
                 status: Optional[Callable[[str], None]] = None, clock: Callable[[], float] = time.monotonic):
        self.caller = tool_caller
        self.registry = registry
        self.bridge = bridge
        self.llm = llm
        self.cfg = config
        self.status = status or (lambda text: None)
        self.clock = clock
        self.llm_calls = 0
        self.limits = ScriptLimits()
        names = [n for n in registry.list_tools() if n not in EXCLUDED_TOOLS]
        self.tool_names = names
        self.tool_functions = [function_name(n) for n in names]

    # ---------------------------------------------------------------- scene helpers
    def _call(self, tool: str, arguments: Dict[str, Any]):
        from .models import ToolCall
        return self.caller.call(ToolCall(tool_name=tool, arguments=arguments))

    def _scene_objects(self) -> List[Dict[str, Any]]:
        reply = self._call("scene.inspect", {})
        if getattr(reply, "success", False) and isinstance(reply.data, dict):
            return list(reply.data.get("objects", []))
        return []

    def _names(self) -> Set[str]:
        return {o.get("name", "") for o in self._scene_objects()}

    @staticmethod
    def _clearance(request: str) -> float:
        try:
            from ..tools.capability import assess_request
            category = assess_request(request).hard_category
        except Exception:  # noqa: BLE001
            category = None
        return {"vehicles": 8.0, "buildings": 12.0, "animals": 5.0, "machines": 4.5}.get(category, 3.5)

    def _free_spot(self, existing: List[Dict[str, Any]], clearance: float = 3.5) -> List[float]:
        occupied = []
        for obj in existing:
            if obj.get("type") in ("MESH", "CURVE") and max(abs(s) for s in (obj.get("scale") or [1, 1, 1])) < 6:
                loc = obj.get("location") or [0, 0, 0]
                occupied.append((loc[0], loc[1]))
        candidates = SLOTS + [(x * 2, y * 2) for x, y in SLOTS[1:]]
        for x, y in candidates:
            if all(math.hypot(x - ox, y - oy) >= clearance for ox, oy in occupied):
                return [float(x), float(y), 0.0]
        return [0.0, 0.0, 0.0]

    def _collisions(self, created: List[str], existing: List[Dict[str, Any]]) -> List[str]:
        measure = getattr(self.bridge, "measure_objects", None)
        if measure is None or not created:
            return []
        try:
            new_box = measure(created)
            if not new_box:
                return []
            found = []
            for obj in existing:
                if obj.get("type") not in ("MESH", "CURVE", "SURFACE"):
                    continue
                box = measure([obj.get("name", "")])
                if not box:
                    continue
                size = [box["max"][k] - box["min"][k] for k in range(3)]
                if max(size) > 30 or (size[2] < 0.05 and size[0] * size[1] > 25):
                    continue
                overlap = [min(new_box["max"][k], box["max"][k]) - max(new_box["min"][k], box["min"][k]) for k in range(3)]
                if all(o > 0.08 for o in overlap):
                    found.append(f"it overlaps the existing object '{obj.get('name')}' (by {overlap[0]:.1f} x {overlap[1]:.1f} x {overlap[2]:.1f} m): "
                                 f"move the whole new object away (its anchor) so there is at least 1 m of free space between them")
            return found[:4]
        except Exception:  # noqa: BLE001
            return []

    def _rollback(self, names: Iterable[str]) -> None:
        for name in reversed(list(names)):
            try:
                self._call("object.delete", {"name": name})
            except Exception:  # noqa: BLE001
                pass

    # ---------------------------------------------------------------- LLM steps
    def _llm(self, system: str, parts: List[Dict[str, Any]], **kw) -> str:
        self.llm_calls += 1
        return self.llm.generate(system, parts, **kw)

    def _writer_system(self) -> str:
        try:
            from ..tools.shader_nodes import RECIPES
            recipes = ", ".join(sorted(RECIPES))
        except Exception:  # noqa: BLE001
            recipes = "fire_flame, ember, smoke_volume, charred_wood, wood_grain, rough_stone, dirt_ground, glass, car_paint, metal_brushed, rubber, water, glow, fabric"
        return WRITER_SYSTEM.replace("{tools}", describe_tools(self.registry, self.tool_names)).replace("{recipes}", recipes)

    def _checked_script(self, system: str, parts: List[Dict[str, Any]], text: str) -> str:
        script = extract_script(text)
        for attempt in range(self.cfg.max_script_retries + 1):
            try:
                validate_script(script, self.tool_functions, self.limits)
                return script
            except ScriptError as exc:
                if attempt >= self.cfg.max_script_retries:
                    raise
                self.status(f"script check failed ({exc}); asking for a fix")
                fix_parts = parts + [{"text": f"Your script was rejected before running: {exc}\n\nHere is the script:\n```python\n{script}\n```\n"
                                              "Return the COMPLETE corrected script in one ```python block."}]
                script = extract_script(self._llm(system, fix_parts, temperature=0.2))
        return script

    def _critique(self, request: str, view_paths: List[str], reference: Optional[str]) -> Critique:
        return critique_renders(self._llm, request, view_paths, reference)

    # ---------------------------------------------------------------- run a script
    def _run(self, script: str, before: Set[str]) -> RunResult:
        def call_tool(tool: str, kwargs: Dict[str, Any]):
            if tool == "object.delete":
                target = str(kwargs.get("name", ""))
                if target in before:
                    from ..tools.base import ToolResult
                    return ToolResult.fail(f"cannot delete '{target}': it existed before this build; only delete objects the script made")
            return self._call(tool, kwargs)
        return run_script(script, call_tool, self.tool_names, self.limits, clock=self.clock)

    # ---------------------------------------------------------------- main
    def build(self, request: str, reference_image: Optional[str] = None, anchor: Optional[Sequence[float]] = None,
              out_dir: Optional[str] = None) -> BuildReport:
        started = self.clock()
        report = BuildReport()
        before_objects = self._scene_objects()
        before = {o.get("name", "") for o in before_objects}
        spot = list(anchor) if anchor else self._free_spot(before_objects, self._clearance(request))
        report.anchor = spot
        folder = out_dir or ""
        if folder:
            os.makedirs(folder, exist_ok=True)
            report.folder = folder

        system = self._writer_system()
        intro = [{"text": f"REQUEST: {request}\n\nANCHOR: build it centred at x={spot[0]}, y={spot[1]}, standing on z=0, front towards -Y.\n"
                          f"Existing objects in the scene (do not touch, keep your object at least 1 m away from them): "
                          f"{', '.join(self._describe(o) for o in before_objects[:14]) or 'none'}"}]
        if reference_image:
            intro.append({"text": "REFERENCE IMAGE (match this look as closely as the tools allow):"})
            intro.append(image_part(reference_image))

        current_names: List[str] = []
        previous_script = ""
        feedback = ""
        history: List[str] = []
        best: Optional[Iteration] = None

        for number in range(1, self.cfg.max_iterations + 1):
            if self.clock() - started > self.cfg.max_seconds:
                report.stopped_reason = "time budget used up"
                break
            iteration = Iteration(number)
            try:
                self.status(f"iteration {number}/{self.cfg.max_iterations}: " + ("writing the script" if number == 1 else "improving the script"))
                if number == 1:
                    text = self._llm(system, intro, temperature=0.5)
                else:
                    parts = list(intro) + [{"text": f"SCORES SO FAR: {', '.join(history)}\n\nYOUR PREVIOUS SCRIPT:\n```python\n{previous_script}\n```\n\n"
                                                    f"{feedback}\n\nReturn the COMPLETE improved script (not a diff). Keep what was right, fix what was "
                                                    "wrong, and do not regress."}]
                    text = self._llm(system, parts, temperature=0.4)
                script = self._checked_script(system, intro, text)
            except BuilderError as exc:
                report.stopped_reason = exc.user_message
                break
            except ScriptError as exc:
                iteration.run_error = f"script rejected: {exc}"
                report.iterations.append(iteration)
                report.stopped_reason = iteration.run_error
                feedback = f"The script was rejected: {exc}"
                previous_script = extract_script(text)
                history.append("rejected")
                continue
            iteration.script = script
            if folder:
                self._save(folder, f"iteration_{number}.py", script)

            if current_names:
                self._rollback(current_names)
                current_names = []
            self.status(f"iteration {number}/{self.cfg.max_iterations}: building")
            run = self._run(script, before)
            iteration.tool_calls = len(run.calls)
            created = sorted(self._names() - before)
            current_names = created
            iteration.objects = created
            previous_script = script

            if not run.ok or not created:
                iteration.run_error = run.error or "the script ran but created no objects"
                feedback = (f"RUN ERROR: {iteration.run_error}\n(Objects it had already made were removed, so start the whole build again.)")
                history.append("error")
                report.iterations.append(iteration)
                continue

            iteration.run_ok = True
            try:
                self.status(f"iteration {number}/{self.cfg.max_iterations}: rendering views")
                views_dir = os.path.join(folder, f"iteration_{number}") if folder else None
                iteration.images = self.bridge.render_views(created, list(self.cfg.views), self.cfg.resolution, views_dir, f"it{number}")
                self.status(f"iteration {number}/{self.cfg.max_iterations}: checking the renders")
                critique = self._critique(request, iteration.images, reference_image)
            except BuilderError as exc:
                iteration.summary = "not reviewed: " + exc.user_message
                report.iterations.append(iteration)
                report.stopped_reason = exc.user_message
                if best is None:
                    best = iteration
                break
            except Exception as exc:  # noqa: BLE001 
                iteration.summary = f"not reviewed: {type(exc).__name__}: {exc}"
                report.iterations.append(iteration)
                report.stopped_reason = iteration.summary
                if best is None:
                    best = iteration
                break

            collisions = self._collisions(created, before_objects)
            iteration.score, iteration.summary = critique.score, critique.summary
            iteration.problems, iteration.keep = list(critique.problems), critique.keep
            for text in collisions:
                iteration.problems.insert(0, {"severity": "high", "where": "placement", "issue": text, "fix": "change the anchor position"})
            if collisions:
                iteration.score = max(0.0, min(iteration.score, self.cfg.target_score - 0.5) - 1.0)
            report.iterations.append(iteration)
            history.append(f"{iteration.score:g}")
            if best is None or iteration.score >= best.score:
                best = iteration
            if iteration.score >= self.cfg.target_score:
                report.reached_target = True
                break
            problems = "\n".join(f"- [{p['severity']}] {p['where']}: {p['issue']} -> {p['fix']}" for p in iteration.problems) or "- (none listed)"
            feedback = (f"REVIEW of your build (score {iteration.score:g}/10): {critique.summary}\nPROBLEMS:\n{problems}\n"
                        f"ALREADY RIGHT (keep): {'; '.join(critique.keep) or '-'}")
            if not critique.raw_ok:
                feedback = "The reviewer's answer was unreadable; re-check proportions, missing parts and attachment yourself and improve."

        if best is not None and best.script and (not report.iterations or report.iterations[-1] is not best):
            self.status(f"restoring the best version (iteration {best.number})")
            if current_names:
                self._rollback(current_names)
            rerun = self._run(best.script, before)
            current_names = sorted(self._names() - before)
            best.objects = current_names
            if not rerun.ok:
                report.stopped_reason = f"could not rebuild the best version: {rerun.error}"
        usable = best is not None and bool(current_names)
        report.success = usable
        report.objects = current_names if usable else []
        if best is not None:
            report.best_score, report.best_iteration, report.script = best.score, best.number, best.script
            report.images = best.images
        if not usable and current_names:
            self._rollback(current_names)
        if not report.stopped_reason and not report.reached_target:
            report.stopped_reason = f"stopped after {len(report.iterations)} iteration(s); best score {report.best_score:g}/10"
        report.llm_calls = self.llm_calls
        report.seconds = self.clock() - started
        if any(i.score > 0 for i in report.iterations):
            REVIEW_LOG.append(time.time())                         # vision review ho chuka
        if folder:
            self._save(folder, "report.json", json.dumps(report.summary(), indent=2))
        return report

    @staticmethod
    def _describe(obj: Dict[str, Any]) -> str:
        loc = obj.get("location") or [0, 0, 0]
        return f"{obj.get('name', '?')}@({loc[0]:.1f},{loc[1]:.1f})"

    @staticmethod
    def _save(folder: str, name: str, text: str) -> None:
        try:
            with open(os.path.join(folder, name), "w", encoding="utf-8") as handle:
                handle.write(text)
        except OSError:
            pass