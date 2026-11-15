"""Real-quality benchmark: runs a fixed set of prompts through the real AI provider inside Blender and scores them.

Unlike the unit tests (fake Blender + mock AI), this measures what users actually get, so you can tell whether a
change made results better or worse.

How to run (the add-on must be installed and enabled, and an API key set):
    Blender > Scripting tab > open this file > Run Script
or headless:
    blender --background --python real_benchmark.py -- --provider gemini --limit 5
    (add --no-team to compare with the single agent, --memory to include remembered preferences)

Each prompt runs in an emptied scene. Per prompt it records: success, seconds, objects created, floating objects,
overlapping objects and (if GEMINI_API_KEY is set) a vision score 0-10 from 2 renders. Results are printed and saved
to ~/BlenderAIAgent/benchmarks/<time>.json — compare two files to see a regression or an improvement.
"""

import json
import os
import sys
import time

import bpy

PROMPTS = [
    "make a wooden table with four legs",
    "make a chair next to a table",
    "put a red book on a table",
    "make a campfire",
    "make a snowman",
    "make a street lamp next to a bench",
    "make a simple house with a red roof",
    "make a bookshelf with books on the shelves",
    "make a car with four wheels",
    "make a small forest with five trees and a rock",
    "make a glass bottle and make it look melted",
    "design a small living room with a sofa, a table and a lamp",
    "make a desk with a computer monitor and a keyboard on it",
    "make a tent, a campfire and a lantern",
    "make a cartoon girl with long blonde hair and glasses",
    "make a low poly mountain with snow on top",
    "make a fence around a small garden",
    "make a lighthouse on a rock",
    "make a dining table with four chairs around it",
    "make a park bench under a tree",
]

GROUND_TOLERANCE = 0.03
MESH_TYPES = {"MESH", "CURVE", "SURFACE", "META", "FONT"}


def _args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    options = {"provider": None, "limit": len(PROMPTS), "vision": True, "team": True, "memory": False}
    for i, arg in enumerate(argv):
        if arg == "--provider" and i + 1 < len(argv):
            options["provider"] = argv[i + 1]
        elif arg == "--limit" and i + 1 < len(argv):
            options["limit"] = int(argv[i + 1])
        elif arg == "--no-vision":
            options["vision"] = False
        elif arg == "--no-team":
            options["team"] = False
        elif arg == "--memory":
            options["memory"] = True
    return options


def _addon():
    for name in ("blender_ai_agent", "bl_ext.user_default.blender_ai_agent"):
        module = sys.modules.get(name)
        if module is not None and hasattr(module, "get_copilot_controller"):
            return module
    import importlib
    return importlib.import_module("blender_ai_agent")


def empty_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    try:
        bpy.data.orphans_purge(do_recursive=True)
    except Exception:  # noqa: BLE001 — older Blender
        pass


def world_box(obj):
    from mathutils import Vector
    corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return ([min(c[k] for c in corners) for k in range(3)], [max(c[k] for c in corners) for k in range(3)])


def _xy_overlap(a, b) -> float:
    dx = min(a[1][0], b[1][0]) - max(a[0][0], b[0][0])
    dy = min(a[1][1], b[1][1]) - max(a[0][1], b[0][1])
    return max(0.0, dx) * max(0.0, dy)


def geometry_checks(names):
    """Floating = lowest point above the ground and not resting on anything. Overlap = two separate objects whose
    boxes intersect by more than 30% of the smaller one (parts of one object usually share a name prefix)."""
    objects = [bpy.data.objects[n] for n in names if n in bpy.data.objects and bpy.data.objects[n].type in MESH_TYPES]
    boxes = {o.name: world_box(o) for o in objects}
    floating = []
    for name, box in boxes.items():
        bottom = box[0][2]
        if bottom <= GROUND_TOLERANCE:
            continue
        supported = any(other != name and abs(obox[1][2] - bottom) <= 0.05 and _xy_overlap(box, obox) > 0
                        or (other != name and obox[0][2] <= bottom <= obox[1][2] and _xy_overlap(box, obox) > 0)
                        for other, obox in boxes.items())
        if not supported:
            floating.append(name)
    overlaps = []
    items = list(boxes.items())
    for i, (a, abox) in enumerate(items):
        for b, bbox in items[i + 1:]:
            if a.split("_")[0] == b.split("_")[0]:
                continue
            dz = min(abox[1][2], bbox[1][2]) - max(abox[0][2], bbox[0][2])
            inter = _xy_overlap(abox, bbox) * max(0.0, dz)
            vol = lambda bx: max(1e-9, (bx[1][0] - bx[0][0]) * (bx[1][1] - bx[0][1]) * (bx[1][2] - bx[0][2]))
            if inter > 0.3 * min(vol(abox), vol(bbox)):
                overlaps.append(f"{a} / {b}")
    return floating, overlaps


def vision_score(addon, prompt, names, folder):
    from blender_ai_agent.agent import self_correct as sc
    cfg = sc.load_builder_config()
    if not cfg.api_key:
        return None, "no GEMINI_API_KEY"
    try:
        images = addon.get_bridge().render_views(names, ["three_quarter", "front"], 384, folder, "bench")
        critique = sc.critique_renders(sc.GeminiClient(cfg).generate, prompt, images)
        return (critique.score if critique.raw_ok else None), critique.summary
    except Exception as exc:  # noqa: BLE001
        return None, f"vision failed: {exc}"


def run():
    options = _args()
    addon = _addon()
    controller = addon.get_copilot_controller(provider_name=options["provider"]) if options["provider"] \
        else addon.get_copilot_controller()
    provider = getattr(controller, "current_provider_name", "?")
    if provider == "mock":
        print("[benchmark] No real AI provider is connected (set GEMINI_API_KEY / GROQ_API_KEY / OPENAI_API_KEY).")
        return None

    controller.team_enabled = options["team"]
    controller.memory_enabled = options["memory"]          # off by default so earlier runs do not leak into scores
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.expanduser("~"), "BlenderAIAgent", "benchmarks")
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for index, prompt in enumerate(PROMPTS[: options["limit"]], 1):
        empty_scene()
        before = set(bpy.data.objects.keys())
        controller._cancelled = False
        started = time.time()
        try:
            result = controller.submit(prompt)
            ok, reply = result.success, result.reply_text or ""
        except Exception as exc:  # noqa: BLE001
            ok, reply = False, f"crash: {exc}"
        seconds = round(time.time() - started, 1)
        created = sorted(set(bpy.data.objects.keys()) - before)
        floating, overlaps = geometry_checks(created)
        score, note = (None, "skipped")
        if options["vision"] and ok and created:
            score, note = vision_score(addon, prompt, created, os.path.join(out_dir, f"{stamp}_{index:02d}"))
        row = {"prompt": prompt, "ok": ok, "seconds": seconds, "objects": len(created), "floating": floating,
               "overlaps": overlaps, "vision_score": score, "vision_note": note, "reply": reply[:300]}
        results.append(row)
        print(f"[benchmark] {index:02d} {'OK ' if ok else 'ERR'} {seconds:6.1f}s objs={len(created):3d} "
              f"float={len(floating)} overlap={len(overlaps)} score={score if score is not None else '-'}  {prompt}")

    scored = [r["vision_score"] for r in results if r["vision_score"] is not None]
    summary = {
        "provider": provider,
        "team": options["team"],
        "routing": type(getattr(controller._agent, "_model_provider", None)).__name__ == "RoutingProvider",
        "prompts": len(results),
        "success_rate": round(sum(r["ok"] for r in results) / max(1, len(results)), 3),
        "avg_seconds": round(sum(r["seconds"] for r in results) / max(1, len(results)), 1),
        "avg_vision_score": round(sum(scored) / len(scored), 2) if scored else None,
        "floating_objects": sum(len(r["floating"]) for r in results),
        "overlaps": sum(len(r["overlaps"]) for r in results),
    }
    path = os.path.join(out_dir, f"{stamp}_{provider}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "results": results}, handle, indent=2)
    print("[benchmark] SUMMARY", json.dumps(summary))
    print(f"[benchmark] saved {path}")
    return summary


if __name__ == "__main__":
    run()
