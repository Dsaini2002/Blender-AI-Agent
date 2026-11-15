"""Local Asset Tools (GitHub CC0 models)"""

import json
import math
import os
import re
from typing import Any, Dict, List, Optional

from .base import Permission, Tool, ToolResult
from .models import PlaceLocalAssetInput, SearchLocalAssetsInput


_HELPER_NAME = re.compile(r"(collider|collision|hitbox|_col$|^ucx_|^ubx_|^usp_|^ucp_)", re.IGNORECASE)


def is_helper_object(name: str) -> bool:
    return bool(_HELPER_NAME.search(name or ""))


def models_dir() -> str:
    env = os.environ.get("BLENDER_AI_MODELS_DIR")
    return os.path.expanduser(env) if env else os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "models")


_INDEX_CACHE: Dict[str, Any] = {}


def load_index() -> List[Dict[str, Any]]:
    path = os.path.join(models_dir(), "index.json")
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"No downloaded models found at {models_dir()}. Run `python download_models.py` once "
            "(from the project folder) to download the CC0 GitHub model collection."
        )
    try:
        stamp = (path, os.path.getmtime(path), os.path.getsize(path))
        if _INDEX_CACHE.get("stamp") == stamp:
            return _INDEX_CACHE["models"]
        with open(path, "r", encoding="utf-8") as handle:
            models = json.load(handle)["models"]
        _INDEX_CACHE.update({"stamp": stamp, "models": models})
        return models
    except (OSError, ValueError, KeyError) as exc:
        raise ValueError(f"Could not read {path}: {exc}. Run `python download_models.py` again.") from exc


def _words(text: str) -> List[str]:
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", text or "")]


def _singular(word: str) -> str:
    if len(word) > 3 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def score_entry(entry: Dict[str, Any], query_words: List[str]) -> float:
    name_words = set(_words(entry.get("name", "")))
    tag_words = set(entry.get("tags", []))
    project_words = set(_words(entry.get("project_name", ""))) | set(_words(entry.get("collection_description", "")))
    total = 0.0
    for word in query_words:
        if word in name_words:
            total += 3.0
        elif any(word in n for n in name_words):       # 'torch' in 'firetorch'
            total += 2.0
        if word in tag_words:
            total += 1.5
        if word in project_words:
            total += 0.5
    return total


def search_index(index: List[Dict[str, Any]], query: str, limit: int = 8, project: Optional[str] = None):
    query_words = [_singular(w) for w in _words(query) or query.lower().split()]
    scored = []
    for entry in index:
        if project and project not in entry.get("project", "").lower() and project not in entry.get("project_name", "").lower():
            continue
        score = score_entry(entry, query_words)
        if score > 0:
            scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], len(pair[1].get("name", "")), pair[1].get("name", "")))
    return [entry for _, entry in scored[:limit]]


def resolve_entry(index: List[Dict[str, Any]], ref: str):
    wanted = (ref or "").strip()
    if not wanted:
        return None, []
    for entry in index:
        if entry["id"] == wanted:
            return entry, []
    low = wanted.lower()
    if "/" in low:
        collection, _, name = low.partition("/")
        hits = [e for e in index if e["name"].lower() == name.strip()
                and collection.strip() in (e.get("project_name", "").lower(), e.get("project", "").lower())]
    else:
        hits = [e for e in index if e["name"].lower() == low]
    if len(hits) == 1:
        return hits[0], []
    return None, hits


def _ref(entry: Dict[str, Any]) -> str:
    return f"{entry.get('project_name', '')}/{entry['name']}"


def _summary(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": entry["id"], "ref": _ref(entry), "name": entry["name"], "collection": entry.get("project_name"),
            "attributes": entry.get("attributes", {}), "size_mb": round(entry.get("size", 0) / 1_000_000, 2)}


class SearchLocalAssetsTool(Tool):
    name = "asset.search_local"
    description = (
        "Searches the DOWNLOADED library of ~990 free CC0 GLB models from GitHub (collections like "
        "MomusPark = park trees/rocks/benches/logs, tomb-chaser = Egyptian props incl. FireTorch, christmas, "
        "medieval-fair, transit, lunar-year, abm...). Give a plain keyword query like 'bench', 'palm tree', "
        "'torch', 'barrel' and get matching models, each with an `id` and a readable `ref` like "
        "'christmas/Fireplace'; then call asset.place_local with that id or ref (copy it EXACTLY). "
        "Optional `project` narrows to one collection. If nothing is downloaded yet the result says to run "
        "download_models.py. For simple props the built-in library.place models (campfire, tent, trees...) "
        "are faster - use this when the user wants more variety or something library.list does not have."
    )
    permission = Permission.READ_ONLY
    input_model = SearchLocalAssetsInput

    def __init__(self, bridge=None):
        self._bridge = bridge

    def run(self, validated_input: SearchLocalAssetsInput) -> ToolResult:
        try:
            index = load_index()
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult.fail(str(exc))

        hits = search_index(index, validated_input.query, validated_input.limit, validated_input.project)
        if not hits:
            return ToolResult.fail(
                f"No downloaded model matches '{validated_input.query}'. Try a simpler/other keyword "
                f"(searched {len(index)} models)."
            )
        return ToolResult.ok({"query": validated_input.query, "count": len(hits), "results": [_summary(h) for h in hits]})


# Typical real-world heights (metres). Downloaded models come in any unit; when an import is far off (more than
# 2x too big or too small) it is rescaled to this height so it fits next to everything else.
REAL_HEIGHTS = {
    "bench": 0.85, "chair": 0.9, "stool": 0.5, "table": 0.75, "desk": 0.75, "sofa": 0.85, "couch": 0.85, "bed": 0.6,
    "streetlamp": 4.5, "streetlight": 4.5, "lamppost": 4.5, "lamp": 1.6, "lantern": 0.4, "torch": 0.6,
    "pine": 7.0, "palm": 8.0, "tree": 6.0, "bush": 1.0, "shrub": 1.0, "boulder": 1.5, "rock": 0.7, "stone": 0.4,
    "barrel": 1.0, "crate": 0.6, "bottle": 0.3, "cup": 0.1, "mug": 0.1, "vase": 0.4, "car": 1.45, "truck": 3.0,
    "bus": 3.2, "house": 6.0, "tent": 1.8, "fence": 1.1, "door": 2.1, "campfire": 0.4, "fountain": 1.5,
    "statue": 2.0, "bin": 0.9, "trashcan": 0.9, "mailbox": 1.2, "bicycle": 1.0, "bike": 1.0, "plant": 0.6, "pot": 0.4,
    "bookshelf": 1.9, "shelf": 1.8, "cabinet": 1.2, "wardrobe": 2.0, "fireplace": 1.2, "well": 1.5, "cart": 1.2,
    "horse": 1.6, "cow": 1.4, "dog": 0.6, "cat": 0.3, "person": 1.75, "man": 1.75, "woman": 1.65, "character": 1.75,
}


def typical_height(*texts: str) -> Optional[float]:
    words = []
    for text in texts:
        words += [_singular(w) for w in _words(text or "")]
    joined = "".join(words)
    for key in ("streetlamp", "streetlight", "lamppost", "trashcan", "bookshelf"):
        if key in joined:
            return REAL_HEIGHTS[key]
    for word in words:
        if word in REAL_HEIGHTS:
            return REAL_HEIGHTS[word]
    return None


class PlaceLocalAssetTool(Tool):
    name = "asset.place_local"
    description = (
        "Imports ONE downloaded CC0 GLB model into the scene and positions it. Pass `asset_id` (the id OR the "
        "readable ref like 'christmas/Fireplace' OR the exact model name, from asset.search_local) or just a "
        "`query` (takes the best match - the simplest and safest choice for plain requests like 'a torch'). "
        "If you pass both, they must agree. ALWAYS read `name`/`collection` in the result and tell the user "
        "exactly which model was placed; if it is not what they asked for, say so and retry. Options: location [x,y,z], scale "
        "(uniform multiplier, 1 = as exported - check the result and rescale if it looks too big/small), "
        "yaw_degrees (turn around the vertical axis). Returns the imported object names. These models are "
        "CC0 (no credit needed)."
    )
    permission = Permission.SAFE_WRITE
    input_model = PlaceLocalAssetInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: PlaceLocalAssetInput) -> ToolResult:
        try:
            index = load_index()
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult.fail(str(exc))

        entry: Optional[Dict[str, Any]] = None
        if validated_input.asset_id:
            entry, candidates = resolve_entry(index, validated_input.asset_id)
            if entry is None and candidates:
                options = ", ".join(_ref(c) for c in candidates[:6])
                return ToolResult.fail(
                    f"'{validated_input.asset_id}' matches several models: {options}. Use one of these refs exactly.")
            if entry is None:
                hint = search_index(index, validated_input.asset_id, 3)
                maybe = f" Did you mean: {', '.join(_ref(h) + ' (id ' + h['id'] + ')' for h in hint)}?" if hint else ""
                return ToolResult.fail(
                    f"No downloaded model with id '{validated_input.asset_id}'.{maybe} Use asset.search_local first.")

            if validated_input.query:
                words = [_singular(w) for w in _words(validated_input.query) or validated_input.query.lower().split()]
                if score_entry(entry, words) == 0:
                    best = search_index(index, validated_input.query, 3)
                    options = ", ".join(f"{_ref(b)} (id {b['id']})" for b in best) or "(none)"
                    return ToolResult.fail(
                        f"asset_id '{validated_input.asset_id}' is '{_ref(entry)}', which does not match the "
                        f"query '{validated_input.query}'. Best matches for the query: {options}.")
        else:
            hits = search_index(index, validated_input.query, 1)
            if not hits:
                return ToolResult.fail(f"No downloaded model matches '{validated_input.query}'.")
            entry = hits[0]

        filepath = os.path.join(models_dir(), *entry["file"].split("/"))
        if not os.path.isfile(filepath):
            return ToolResult.fail(f"Model file missing on disk: {filepath}. Run download_models.py again.")

        try:
            imported = self._bridge.import_model(filepath=filepath)
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        names = {id(obj): obj.name for obj in imported}
        removed_helpers = []
        removed_ids = set()
        for obj in imported:
            if is_helper_object(names[id(obj)]) and self._bridge.delete_object(names[id(obj)]):
                removed_helpers.append(names[id(obj)])
                removed_ids.add(id(obj))
        imported = [obj for obj in imported if id(obj) not in removed_ids]

        yaw = math.radians(validated_input.yaw_degrees)
        loc = list(validated_input.location)
        path_note = None
        if float(loc[2]) <= 0.05:                     # standing on the ground: keep it off paths
            from . import paths as _paths
            live = _paths.live_paths(self._bridge)
            if live:
                x, y, moved_off, _facing = _paths.clear_spot(float(loc[0]), float(loc[1]), 0.45, live)
                if moved_off:
                    path_note = (f"[{loc[0]:g}, {loc[1]:g}] was on {', '.join(moved_off)}; "
                                 f"placed at the edge instead: [{x:.2f}, {y:.2f}]")
                    loc = [round(x, 3), round(y, 3), loc[2]]
        scale = validated_input.scale
        roots = [o for o in imported if getattr(o, "parent", None) is None]
        for root in roots:
            ox, oy, oz = root.location
            ox, oy, oz = ox * scale, oy * scale, oz * scale
            rx, ry = ox * math.cos(yaw) - oy * math.sin(yaw), ox * math.sin(yaw) + oy * math.cos(yaw)
            rotation = list(root.rotation_euler)
            rotation[2] += yaw
            self._bridge.transform_object(
                root.name,
                location=[loc[0] + rx, loc[1] + ry, loc[2] + oz],
                rotation=rotation,
                scale=[s * scale for s in root.scale],
            )

        auto_scale, size = self._fit_to_real_size(roots, entry, validated_input, loc)
        baked = self._bake_scale(roots)

        return ToolResult.ok({
            "id": entry["id"], "name": entry["name"], "collection": entry.get("project_name"),
            "objects": [o.name for o in imported], "roots": [o.name for o in roots],
            "location": list(loc), "scale": scale, "license": entry.get("license", "CC0"),
            "removed_helpers": removed_helpers, "auto_scale": auto_scale, "size": size,
            "scale_baked": baked,
            **({"moved_off_path": path_note} if path_note else {}),
        })

    def _bake_scale(self, roots):
        """Leave every root at scale 1.0 (its import unit scale moved into the mesh), so a later
        object.transform(scale=[1, 1, 1]) cannot blow the model up 100x."""
        bake = getattr(self._bridge, "bake_scale", None)
        if bake is None:
            return False
        done = False
        for root in roots:
            try:
                done = bool(bake(root.name)) or done
            except Exception:  # noqa: BLE001
                pass
        return done

    def _fit_to_real_size(self, roots, entry, v, loc):
        """Rescale a wildly mis-sized import to a typical real height (only when the caller left scale at 1) and
        make it stand on the placement height. Returns (factor applied or None, [x, y, z] size)."""
        measure = getattr(self._bridge, "measure_objects", None)
        names = [r.name for r in roots]
        if measure is None or not names:
            return None, None
        try:
            box = measure(names)
        except Exception:  # noqa: BLE001
            return None, None
        if not box:
            return None, None
        height = box["max"][2] - box["min"][2]
        factor = None
        target = typical_height(v.query or "", entry.get("name", ""), " ".join(entry.get("tags", [])[:4]))
        if target and abs(v.scale - 1.0) < 1e-6 and height > 1e-4:
            ratio = height / target
            if ratio > 2.0 or ratio < 0.5:
                factor = target / height
                for root in roots:
                    rl = list(root.location)
                    self._bridge.transform_object(
                        root.name,
                        location=[loc[0] + (rl[0] - loc[0]) * factor, loc[1] + (rl[1] - loc[1]) * factor,
                                  loc[2] + (rl[2] - loc[2]) * factor],
                        scale=[s * factor for s in root.scale])
                box = measure(names) or box
        bottom = box["min"][2]
        if abs(bottom - loc[2]) > 0.01:                       # stand on the placement height, not float / sink
            for root in roots:
                rl = list(root.location)
                self._bridge.transform_object(root.name, location=[rl[0], rl[1], rl[2] + (loc[2] - bottom)])
            box = measure(names) or box
        size = [round(box["max"][k] - box["min"][k], 3) for k in range(3)]
        return (round(factor, 4) if factor else None), size