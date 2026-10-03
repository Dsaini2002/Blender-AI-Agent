#!/usr/bin/env python3
"""
download_models.py
===================
Hinglish: GitHub ke CC0 3D model registry (ToxSam/open-source-3D-assets) se saare GLB models
aapke PC par download karta hai, aur `index.json` banata hai jisse Blender AI Agent unhe naam
se dhoondh kar scene mein laga sake (asset.search_local / asset.place_local).

  - 991 models, 18 collections, lagbhag 2.25 GB, sab CC0 (public domain)
  - sirf Python standard library — kuch install nahi karna
  - resume-safe: dobara chalane par jo file pehle se hai wo skip hoti hai

Examples:
  python download_models.py --list                         # collections aur unke size dekho
  python download_models.py                                # sab kuch (size poochh kar)
  python download_models.py --yes                          # bina poochhe sab kuch
  python download_models.py --only momuspark,christmas     # sirf ye collections
  python download_models.py --max-mb 20                    # 20 MB se badi files chhod do
  python download_models.py --dest D:\\Models              # kahin aur rakho

Default folder: ~/BlenderAIAgent/models  (env var BLENDER_AI_MODELS_DIR se badal sakte ho)
"""

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REGISTRY_BASE = "https://raw.githubusercontent.com/ToxSam/open-source-3d-assets/main/data/"
USER_AGENT = "Blender-AI-Agent-ModelDownloader/1.0 (+https://github.com/Dsaini2002/Blender-AI-Agent)"


def default_dest() -> Path:
    env = os.environ.get("BLENDER_AI_MODELS_DIR")
    return Path(env).expanduser() if env else Path.home() / "BlenderAIAgent" / "models"


# ---------------------------------------------------------------------------
# Network helpers (tests mein inhe fake se badla jaata hai)
# ---------------------------------------------------------------------------
def fetch_bytes(url: str, timeout: int = 60, retries: int = 3) -> bytes:
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
            time.sleep(min(2 * attempt, 6))
    raise RuntimeError(f"download failed after {retries} tries: {url} ({last_error})")


def fetch_json(url: str):
    return json.loads(fetch_bytes(url).decode("utf-8"))


# ---------------------------------------------------------------------------
# Registry -> entries
# ---------------------------------------------------------------------------
def load_registry(fetch=fetch_json):
    """Return (projects, {project_id: [asset, ...]})."""
    projects = fetch(REGISTRY_BASE + "projects.json")
    assets = {}
    for project in projects:
        assets[project["id"]] = fetch(REGISTRY_BASE + project["asset_data_file"])
    return projects, assets


def safe_name(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("._") or "model"


def split_words(name: str):
    """'FireTorch01_Art' -> ['fire', 'torch', '01', 'art']"""
    return [w.lower() for w in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", name)]


def make_entry(project: dict, asset: dict) -> dict:
    url = asset["model_file_url"]
    filename = safe_name(os.path.basename(url.split("?")[0]))
    attributes = {a.get("trait_type", ""): str(a.get("value", ""))
                  for a in (asset.get("metadata", {}).get("attributes") or []) if a.get("trait_type")}
    tags = split_words(asset.get("name", ""))
    for value in attributes.values():
        tags.extend(split_words(value) or [value.lower()])
    return {
        "id": asset["id"],
        "name": asset.get("name", filename),
        "project": project["id"],
        "project_name": project.get("name", ""),
        "collection_description": project.get("description", ""),
        "attributes": attributes,
        "tags": sorted({t for t in tags if t}),
        "file": f"{safe_name(project['name'])}/{filename}",
        "size": int(asset.get("metadata", {}).get("file_size") or 0),
        "url": url,
        "license": project.get("license", "CC0"),
        "format": asset.get("format", "GLB"),
    }


def select_projects(projects, only):
    """`only` = ['momuspark', 'christmas'] -> un projects ko (naam ya id mein substring match). Khaali = sab."""
    if not only:
        return list(projects)
    wanted = [o.strip().lower() for o in only if o.strip()]
    chosen = [p for p in projects if any(w in p["id"].lower() or w in p["name"].lower() for w in wanted)]
    return chosen


def build_entries(projects, assets_by_project, only=None, max_mb=None):
    entries = []
    for project in select_projects(projects, only):
        for asset in assets_by_project.get(project["id"], []):
            if asset.get("is_draft") or asset.get("is_public") is False:
                continue
            if not asset.get("model_file_url", "").lower().endswith((".glb", ".gltf")):
                continue
            entry = make_entry(project, asset)
            if max_mb is not None and entry["size"] > max_mb * 1_000_000:
                continue
            entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def download_entry(entry, dest: Path, fetch=fetch_bytes, force=False) -> str:
    """Return 'downloaded' | 'skipped' | 'failed: <why>'. Half-written file kabhi final naam par nahi aati."""
    target = dest / entry["file"]
    if target.is_file() and not force:
        if not entry["size"] or target.stat().st_size == entry["size"]:
            return "skipped"
    try:
        data = fetch(entry["url"])
        if not data.startswith(b"glTF") and entry["file"].lower().endswith(".glb"):
            return "failed: not a valid .glb file"
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        partial.write_bytes(data)
        os.replace(partial, target)
        return "downloaded"
    except Exception as exc:  # noqa: BLE001
        return f"failed: {exc}"


def write_index(dest: Path, entries) -> int:
    """index.json mein sirf wahi models jo disk par asal mein maujood hain."""
    present = [e for e in entries if (dest / e["file"]).is_file()]
    dest.mkdir(parents=True, exist_ok=True)
    payload = {"source": "https://github.com/ToxSam/open-source-3D-assets", "license": "CC0 1.0 (public domain)",
               "count": len(present), "models": present}
    (dest / "index.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    return len(present)


def human(num_bytes: int) -> str:
    return f"{num_bytes / 1_000_000:.0f} MB" if num_bytes >= 1_000_000 else f"{num_bytes / 1000:.0f} KB"


def run(argv=None, fetch_json_fn=fetch_json, fetch_bytes_fn=fetch_bytes, input_fn=input, out=print) -> int:
    parser = argparse.ArgumentParser(description="Download CC0 GLB models from GitHub for Blender AI Agent.")
    parser.add_argument("--dest", default=None, help="folder jahan models rakhne hain (default ~/BlenderAIAgent/models)")
    parser.add_argument("--only", default="", help="comma-separated collection naam/id, jaise momuspark,christmas")
    parser.add_argument("--list", action="store_true", help="sirf collections aur size dikhao")
    parser.add_argument("--yes", "-y", action="store_true", help="size poochhe bina download shuru karo")
    parser.add_argument("--max-mb", type=float, default=None, help="isse badi files skip karo")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--force", action="store_true", help="pehle se maujood files dobara download karo")
    args = parser.parse_args(argv)

    dest = Path(args.dest).expanduser() if args.dest else default_dest()

    out("Registry padh raha hoon (github.com/ToxSam/open-source-3D-assets) ...")
    projects, assets = load_registry(fetch_json_fn)
    only = [x for x in args.only.split(",") if x.strip()]

    if args.list:
        for project in select_projects(projects, only):
            entries = build_entries([project], assets, max_mb=args.max_mb)
            out(f"  {project['name']:28s} {len(entries):4d} models  {human(sum(e['size'] for e in entries)):>8s}   {project.get('description', '')[:60]}")
        return 0

    chosen = select_projects(projects, only)
    if only and not chosen:
        out(f"Koi collection nahi mila: {only}. `--list` se naam dekho.")
        return 2

    entries = build_entries(projects, assets, only=only, max_mb=args.max_mb)
    total = sum(e["size"] for e in entries)
    todo = [e for e in entries if args.force or not (dest / e["file"]).is_file()]
    out(f"{len(entries)} models, {human(total)} total (CC0). Destination: {dest}")
    out(f"Abhi download hona baaki: {len(todo)} files.")

    if todo and not args.yes:
        answer = input_fn("Download shuru karun? [y/N] ").strip().lower()
        if answer not in ("y", "yes", "haan", "ha"):
            out("Cancel.")
            return 1

    stats = {"downloaded": 0, "skipped": 0, "failed": 0}
    failures = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {pool.submit(download_entry, e, dest, fetch_bytes_fn, args.force): e for e in entries}
            for done, future in enumerate(concurrent.futures.as_completed(futures), 1):
                result = future.result()
                key = "failed" if result.startswith("failed") else result
                stats[key] += 1
                if key == "failed":
                    failures.append((futures[future]["name"], result))
                if done % 25 == 0 or done == len(entries):
                    out(f"  {done}/{len(entries)}  (naye {stats['downloaded']}, pehle se {stats['skipped']}, fail {stats['failed']})")
    except KeyboardInterrupt:
        out("Roka gaya — jo download ho chuka hai uska index bana raha hoon (dobara chalane par aage badhega).")
    finally:
        count = write_index(dest, entries)

    out(f"Index ban gaya: {dest / 'index.json'}  ({count} models ready)")
    for name, why in failures[:10]:
        out(f"  FAIL {name}: {why}")
    out("Ab Blender AI Agent mein likho:  find a bench model   /   place a torch from the downloaded models")
    return 0 if not failures else 3


if __name__ == "__main__":
    sys.exit(run())