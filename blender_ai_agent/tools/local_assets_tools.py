"""
Local Asset Tools (GitHub CC0 models)
======================================
Hinglish: `download_models.py` jo 991 CC0 GLB models aapke PC par utaarta hai, unhe yahan se
agent search karta hai (asset.search_local) aur scene mein laga deta hai (asset.place_local).
Download ke bina ye tools saaf message dete hain ki pehle script chalao.

Index ki jagah: env var BLENDER_AI_MODELS_DIR, warna ~/BlenderAIAgent/models/index.json
"""

import json
import math
import os
import re
from typing import Any, Dict, List, Optional

from .base import Permission, Tool, ToolResult
from .models import PlaceLocalAssetInput, SearchLocalAssetsInput


# Hinglish: Kai GLB models ke saath ek "collision proxy" box/mesh aata hai (physics ke liye, jaise
# `Barrel_collider`). Scene mein wo ek safed dibba dikhta hai aur asli model uske andar ghus jaata hai —
# isliye import ke baad aise helper objects hata dete hain.
_HELPER_NAME = re.compile(r"(collider|collision|hitbox|_col$|^ucx_|^ubx_|^usp_|^ucp_)", re.IGNORECASE)


def is_helper_object(name: str) -> bool:
    """True agar ye naam collision-proxy / helper mesh jaisa lagta hai (Barrel_collider, UCX_Wall...)."""
    return bool(_HELPER_NAME.search(name or ""))


def models_dir() -> str:
    env = os.environ.get("BLENDER_AI_MODELS_DIR")
    return os.path.expanduser(env) if env else os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "models")


_INDEX_CACHE: Dict[str, Any] = {}


def load_index() -> List[Dict[str, Any]]:
    """
    index.json padho. Na mile / kharab ho to FileNotFoundError / ValueError (tool use fail message mein badalta hai).
    Hinglish: skills har message par isse poochhti hain, isliye file badalne tak (mtime) memory mein cache hota hai.
    """
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
    """
    Hinglish: `asset_id` ke taur par LLM kabhi opaque id galat copy kar deta hai (jaise 'xyz-006' vs
    'christmas-006') aur galat model lag jaata hai. Isliye insaani-padhne-layak naam bhi maante hain:
        'medieval-fair-003'          -> exact id
        'christmas/Fireplace'        -> collection/naam
        'Fireplace'                  -> exact naam (agar sirf ek model ka ho)
    Return (entry, candidates). entry None + candidates khaali = nahi mila; candidates bhari = ambiguous.
    """
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

            # Hinglish: id + query dono diye hain to unka match hona zaroori hai — warna galat id copy hui hai
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

        # Collision proxies (Barrel_collider...) scene mein ek safed dibba ban jaate hain — hata do.
        # Hinglish: IMPORTANT — Blender mein delete hone ke baad object ka `.name` padhna crash karta hai
        # ("StructRNA of type Object has been removed"). Isliye saare naam PEHLE padh lete hain, aur
        # filter naam se nahi, object identity (id) se karte hain.
        names = {id(obj): obj.name for obj in imported}
        removed_helpers = []
        removed_ids = set()
        for obj in imported:
            if is_helper_object(names[id(obj)]) and self._bridge.delete_object(names[id(obj)]):
                removed_helpers.append(names[id(obj)])
                removed_ids.add(id(obj))
        imported = [obj for obj in imported if id(obj) not in removed_ids]

        # Hinglish: glb ke andar hierarchy ho sakti hai — sirf ROOT objects (jinka parent nahi) ko
        # move/scale/rotate karte hain, bachche unke saath chalte hain.
        yaw = math.radians(validated_input.yaw_degrees)
        loc = validated_input.location
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

        return ToolResult.ok({
            "id": entry["id"], "name": entry["name"], "collection": entry.get("project_name"),
            "objects": [o.name for o in imported], "roots": [o.name for o in roots],
            "location": list(loc), "scale": scale, "license": entry.get("license", "CC0"),
            "removed_helpers": removed_helpers,
        })