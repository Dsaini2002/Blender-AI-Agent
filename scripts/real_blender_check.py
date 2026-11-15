"""Run the add-on inside REAL Blender (the `bpy` module from PyPI) and check what the fake-bpy unit tests cannot.

    python -m venv .bpyenv && .bpyenv/bin/pip install bpy==5.2.1
    .bpyenv/bin/python scripts/real_blender_check.py            # add --render for the EEVEE check renders

What it does: registers the add-on, builds a whole hostel campus with the real tools (building, boundary wall with
gate sign, courts with their nets / hoops, bicycle parking, path, light, camera), sorts it into collections, saves a
.blend, checks that the automatic geometry check reports nothing false about the generated parts, and that
"Revert AI Changes" puts the scene back. Exit code 0 = all good.
"""

import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
WORK = tempfile.mkdtemp(prefix="aiagent_real_")
os.environ["BLENDER_AI_LOG_DIR"] = os.path.join(WORK, "logs")
os.environ["BLENDER_AI_RECENT_FILE"] = os.path.join(WORK, "recent.json")
os.environ["HOME"] = WORK                                     # scene.save writes under ~/BlenderAIAgent/scenes
os.environ["USERPROFILE"] = WORK

import bpy  # noqa: E402

import blender_ai_agent as addon  # noqa: E402
from blender_ai_agent.agent.models import ToolCall  # noqa: E402

FAILURES = []


def check(ok, what):
    print(("  ok   " if ok else "  FAIL ") + what)
    if not ok:
        FAILURES.append(what)


def main(render: bool) -> int:
    print(f"Blender {bpy.app.version_string}")
    addon.register()
    caller = addon.get_tool_caller()
    caller.approver = None
    bridge = addon.get_bridge()

    def call(tool, **args):
        started = time.time()
        result = caller.call(ToolCall(tool_name=tool, arguments=args))
        check(result.success, f"{tool} ({time.time() - started:.1f}s) {'' if result.success else result.error}")
        return result

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add(location=(70, 70, 1))
    bpy.context.active_object.name = "UserCube"

    from blender_ai_agent.ui import run_state
    check(run_state.take_checkpoint(bridge, "campus") == "full", "checkpoint saved as a .blend library")

    building = call("mesh.building", name="hostel", shape="U", floors=6, floor_height=3.2, rooms=180,
                    sign_text="IIT STUDENT HOSTEL")
    check(150 <= building.data.get("rooms", 0) <= 200, "150-200 rooms")
    call("mesh.terrain", name="campus_ground", size=[140, 140], style="flat", height=0.0)
    call("material.recipe", recipe="grass", assign_to=["campus_ground"])       # no name: named for you
    call("mesh.boundary_wall", name="campus_wall", size=[120, 120], sign_text="IIT STUDENT HOSTEL")
    courts = call("mesh.field_markings", sport="basketball", name="bb_court", location=[42, -10, 0.02])
    check(len(courts.data.get("equipment", [])) == 2, "basketball court got its 2 hoops")
    call("mesh.field_markings", sport="badminton", name="bd_court", location=[-42, -10, 0.02])
    again = call("library.place", model="basketball_hoop", location=[42, -10, 0])
    check(bool(again.data.get("skipped")), "a second hoop in the court centre is refused")
    call("library.place", model="bicycle_parking", location=[20, -40, 0])
    call("library.place", model="park_bench", location=[0, 8, 0])
    call("curve.create", name="main_path", points=[[0, -60, 0.02], [0, -32, 0.02]], profile="flat", width=4)
    call("material.recipe", recipe="concrete", assign_to=["main_path"])
    call("light.create", light_type="SUN", energy=4, rotation=[0.8, 0.2, 0.6])
    call("camera.create", location=[0, -120, 95], rotation=[0.9, 0, 0])
    call("scene.organize", collections=["Hostel_Building", "Rooms", "Furniture", "Sports", "Landscaping",
                                        "Lighting", "Cameras"])
    rooms = bpy.data.collections.get("Rooms")
    check(rooms is not None and "hostel_rooms" in rooms.objects, "rooms sorted into the Rooms collection")
    saved = call("scene.save", filename="IIT_Hostel_Campus.blend")
    check(os.path.isfile(saved.data.get("filepath", "")), "the .blend file exists")

    # editing what is there: a new roof design and colours, then a recolour
    before = len(bpy.data.objects)
    edited = call("mesh.building", name="hostel", roof="hip", wall_color="cream")
    check(edited.data.get("rebuilt") and edited.data.get("floors") == 6 and len(bpy.data.objects) == before,
          "roof design changed in place (same floors, no duplicates)")
    call("object.recolor", names=["campus_wall_wall"], color="light grey")
    for model, where in (("double_bed", [-8, 8, 0]), ("chandelier", [-8, 8, 3.0]), ("wall_art", [-8, 10, 1.6]),
                         ("nightstand", [-9.5, 9, 0]), ("table_lamp", [-9.5, 9, 0.58]), ("rug", [-8, 7, 0]),
                         ("armchair", [-5, 6, 0]), ("ceiling_lamp", [-5, 8, 3.0])):
        placed = call("library.place", model=model, location=where)
        if model == "ceiling_lamp":
            check(placed.data.get("model") == "pendant_light", "a ceiling lamp is a pendant light, not a street lamp")

    from blender_ai_agent.agent.scene_checks import geometry_problems
    names = [o.name for o in bpy.data.objects if o.name != "UserCube"]       # what the AI made
    problems = geometry_problems(bridge, names)
    check(not problems, f"automatic geometry check is clean ({len(problems)} problem(s)) "
                        + json.dumps(problems)[:300])

    # two pieces of furniture in one place must be found, and the suggested move must clear it
    call("library.place", model="bookshelf", location=[30, 30, 0])
    call("library.place", model="study_table", location=[30, 29.9, 0])
    clash = [p for p in geometry_problems(bridge, [o.name for o in bpy.data.objects if o.name != "UserCube"])
             if "stands inside" in p["issue"]]
    check(len(clash) == 1 and clash[0]["where"] == "study_table", f"desk inside a bookshelf is found ({len(clash)})")
    if clash:
        offset = json.loads(clash[0]["fix"].split("offset=")[1].split(")")[0])
        call("object.move_by", names=["study_table"], offset=offset)
        again = [p for p in geometry_problems(bridge, [o.name for o in bpy.data.objects if o.name != "UserCube"])
                 if "stands inside" in p["issue"]]
        check(not again, "the suggested object.move_by clears it")

    if render:
        started = time.time()
        paths = bridge.render_views(names, ["three_quarter"], 256, os.path.join(WORK, "checks"), "check")
        check(any("_cutaway_" in p for p in paths), f"check renders incl. the cutaway ({time.time() - started:.0f}s)")

    message = run_state.revert(bridge)
    left = sorted(o.name for o in bpy.context.scene.objects)
    check(left == ["UserCube"], f"Revert AI Changes: {message} -> {left}")

    agent_run(addon, render)
    checklist_run(addon, render)
    stop_run(addon)
    resume_run(addon)
    skill_run(addon)

    for name, key in (("gemini", "GEMINI_API_KEY"), ("claude", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")):
        os.environ[key] = "test-key"                       # no network call: only building the Copilot
        addon.reset_providers()
        controller = addon.get_copilot_controller(provider_name=name)
        check(controller.current_provider_name == name and controller.team_enabled,
              f"Copilot starts with {name} (team mode on)")
        os.environ.pop(key, None)
    addon.reset_providers()

    addon.unregister()
    print(f"\n{len(FAILURES)} failure(s). Work folder: {WORK}")
    return 1 if FAILURES else 0


class _Reply:
    def __init__(self, data):
        self._raw = json.dumps(data).encode("utf-8")
        self.status = 200

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def agent_run(addon, render: bool) -> None:
    """A whole Generate click with Claude, the network replaced by scripted answers: team plan -> role steps
    with tool calls -> automatic check (renders + vision) -> done."""
    from unittest import mock

    from blender_ai_agent import net

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    from blender_ai_agent.tools import field_markings
    field_markings.COURTS.clear()
    os.makedirs(os.path.join(WORK, "BlenderAIAgent"), exist_ok=True)
    with open(os.path.join(WORK, "BlenderAIAgent", "autoverify.json"), "w") as handle:
        json.dump({"mode": "full" if render else "console", "views": ["three_quarter"], "resolution": 256,
                   "max_rounds": 2}, handle)

    def tool(tool_name, **args):
        return {"type": "tool_use", "id": f"t{time.time_ns()}", "name": tool_name.replace(".", "__"), "input": args}

    steps = {
        "layout": [tool("mesh.building", name="hostel", shape="U", floors=6, rooms=180, sign_text="IIT STUDENT HOSTEL"),
                   tool("mesh.terrain", name="campus_ground", size=[140, 140], style="flat", height=0.0),
                   tool("material.recipe", recipe="grass", assign_to=["campus_ground"])],
        "modeling": [tool("mesh.field_markings", sport="basketball", name="bb_court", location=[42, -10, 0.02]),
                     tool("mesh.boundary_wall", name="campus_wall", size=[120, 120], sign_text="IIT HOSTEL"),
                     tool("library.place", model="bicycle_parking", location=[20, -40, 0])],
        "lighting": [tool("light.create", light_type="SUN", energy=4, rotation=[0.8, 0.2, 0.6]),
                     tool("camera.create", location=[0, -120, 95], rotation=[0.9, 0, 0])],
        "finish": [tool("scene.organize", collections=["Hostel_Building", "Rooms", "Furniture", "Sports",
                                                       "Landscaping", "Lighting", "Cameras"])],
    }
    done = set()
    seen = {"plans": 0, "steps": 0, "vision": 0}

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data or b"{}")
        system = body.get("system") or ""
        if "You lead a small 3D team" in system:
            seen["plans"] += 1
            plan = {"steps": [{"role": "architect", "task": "hostel building and ground"},       # synonyms on purpose
                              {"role": "landscaping", "task": "court, wall, cycle parking"},
                              {"role": "cameras", "task": "sun and camera"},
                              {"role": "finish", "task": "collections"}]}
            return _Reply({"content": [{"type": "text", "text": "```json\n" + json.dumps(plan) + "\n```"}]})
        content = body["messages"][0]["content"]
        if isinstance(content, list):                                  # the picture check
            seen["vision"] += 1
            return _Reply({"content": [{"type": "text", "text": json.dumps(
                {"score": 10, "summary": "complete campus", "checklist": [{"item": "hostel", "present": True}],
                 "problems": [], "keep": ["all"]})}]})
        import re as _re
        found = _re.search(r"TEAM MODE . step (\d+) of", system)
        role = list(steps)[int(found.group(1)) - 1] if found else None
        role = None if role in done else role
        if role is None:
            return _Reply({"content": [{"type": "text", "text": "Done."}]})
        last = body["messages"][-1]["content"]
        if "[Tool result]" in last:                                     # the step's tools ran: finish it
            done.add(role)
            return _Reply({"content": [{"type": "text", "text": f"{role} done."}]})
        seen["steps"] += 1
        return _Reply({"content": steps[role], "stop_reason": "tool_use"})

    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    os.environ.pop("GEMINI_API_KEY", None)
    addon.reset_providers()
    try:
        with mock.patch.object(net, "urlopen", fake_urlopen):
            controller = addon.get_copilot_controller(provider_name="claude")
            started = time.time()
            result = controller.submit("Create a realistic IIT student hostel campus: G+5 U-shaped hostel, "
                                       "basketball court, boundary wall with gate, cycle parking, collections.")
        print(f"  agent run: {time.time() - started:.0f}s; plans={seen['plans']} steps={seen['steps']} "
              f"vision={seen['vision']}")
        check(result.success, "Generate finished: " + (result.reply_text or "").splitlines()[0][:100])
        check(seen["plans"] >= 1 and len(done) == 4, f"team mode ran all 4 role steps ({sorted(done)})")
        names = {o.name for o in bpy.data.objects}
        for wanted in ("hostel_walls", "bb_court", "campus_wall_gate", "bicycle_parking_roof"):
            check(wanted in names, f"{wanted} was built")
        check(bpy.data.collections.get("Rooms") is not None, "collections made")
        if render:
            check(seen["vision"] >= 1 and "vision 10/10" in (result.reply_text or ""), "picture check ran with Claude")
            checks_root = os.path.join(WORK, "BlenderAIAgent", "checks")
            rounds = sorted(os.listdir(checks_root)) if os.path.isdir(checks_root) else []
            review = os.path.join(checks_root, rounds[-1], "review.txt") if rounds else ""
            check(bool(review) and os.path.isfile(review) and "score: 10/10" in open(review, encoding="utf-8").read(),
                  f"review.txt next to the check images ({review})")
        log = getattr(controller, "last_log_path", "")
        if log and os.path.isfile(log):
            events = [e["event"] for e in json.load(open(log, encoding="utf-8"))["events"]]
            check("team.plan" in events, "the run log records the team plan")
        report = getattr(controller, "last_report_path", "")
        check(bool(report) and os.path.isfile(report), f"readable run report written ({report})")
        from blender_ai_agent.observability.run_trace import live_path
        with open(live_path(), encoding="utf-8") as handle:
            live = handle.read()
        check("FINISHED" in live and "TOOL   mesh.building" in live, "live trace has every step and the finish")
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        addon.reset_providers()


def checklist_run(addon, render: bool) -> None:
    """The new flow end to end: the AI writes the checklist first -> builds (badly placed on purpose) -> saves ->
    the AI places every thing (books + laptop ON the table) -> the deep check looks from every angle + zoom-ins ->
    the final scene is saved again and checked on disk."""
    import re as _re
    from unittest import mock

    from blender_ai_agent import net

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    with open(os.path.join(WORK, "BlenderAIAgent", "autoverify.json"), "w") as handle:
        json.dump({"mode": "full" if render else "console", "resolution": 192, "max_rounds": 1}, handle)

    def tool(tool_name, **args):
        return {"type": "tool_use", "id": f"t{time.time_ns()}", "name": tool_name.replace(".", "__"), "input": args}

    build = [
        tool("object.create", name="table_top", primitive="CUBE", location=[0, 0, 0.75]),
        tool("object.transform", name="table_top", scale=[0.6, 0.4, 0.025]),
    ] + [tool("object.create", name=f"table_leg_{i}", primitive="CUBE", location=[x, y, 0.37])
         for i, (x, y) in enumerate([(-0.55, -0.35), (0.55, -0.35), (-0.55, 0.35), (0.55, 0.35)], 1)] + [
        tool("object.transform", name=f"table_leg_{i}", scale=[0.03, 0.03, 0.37]) for i in range(1, 5)] + [
        tool("object.create", name="book_1", primitive="CUBE", location=[-2, 1, 0.015]),       # on the floor
        tool("object.transform", name="book_1", scale=[0.12, 0.085, 0.015]),
        tool("object.create", name="book_2", primitive="CUBE", location=[-0.55, -0.35, 0.3]),  # inside a leg
        tool("object.transform", name="book_2", scale=[0.12, 0.085, 0.015]),
        tool("object.create", name="laptop", primitive="CUBE", location=[0.2, 0, 1.6]),        # floating
        tool("object.transform", name="laptop", scale=[0.17, 0.12, 0.01]),
        tool("object.create", name="lamp", primitive="CYLINDER", location=[2.5, 2, 0.25]),
        tool("object.transform", name="lamp", scale=[0.12, 0.12, 0.25]),
        tool("material.recipe", recipe="wood_grain", assign_to=["table_top", "table_leg_1", "table_leg_2",
                                                                 "table_leg_3", "table_leg_4"]),
        tool("material.recipe", recipe="paint", assign_to=["book_1", "book_2", "laptop", "lamp"]),
        tool("camera.create", location=[3.5, -3.5, 2.6], rotation=[1.1, 0, 0.78]),
        tool("scene.save", filename="desk_test.blend"),
    ]
    seen = {"plan": 0, "place": 0, "vision": 0, "images": 0, "tools_sent": 0, "build_turns": 0, "zoom": 0}
    state = {"built": False}

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data or b"{}")
        system = body.get("system") or ""
        content = body["messages"][0]["content"]
        if isinstance(content, list) and any(c.get("type") == "image" for c in content):
            seen["vision"] += 1
            seen["images"] += sum(1 for c in content if c.get("type") == "image")
            seen["zoom"] += sum(1 for c in content if c.get("type") == "text" and "ZOOMED-IN" in c.get("text", ""))
            text = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
            seen["checklist_sent"] = "CHECKLIST" in text and "laptop" in text
            return _Reply({"content": [{"type": "text", "text": json.dumps({
                "score": 10, "summary": "table with books, laptop and lamp", "problems": [], "keep": ["all"],
                "checklist": [{"item": "table", "wanted": 1, "seen": 1, "present": True, "where_ok": True},
                              {"item": "book", "wanted": 2, "seen": 2, "present": True, "where_ok": True},
                              {"item": "laptop", "wanted": 1, "seen": 1, "present": True, "where_ok": True},
                              {"item": "lamp", "wanted": 1, "seen": 1, "present": True, "where_ok": True}],
                "measured": []})}]})
        if "You are the planner of a Blender AI copilot" in system:
            seen["plan"] += 1
            return _Reply({"content": [{"type": "text", "text": json.dumps({
                "kind": "new", "summary": "a table with two books and a laptop on it, and a lamp",
                "checklist": [{"item": "table", "count": 1, "position": "", "size": "1.2 x 0.8 x 0.78 m"},
                              {"item": "book", "count": 2, "position": "on the table", "size": "0.24 x 0.17 x 0.03 m"},
                              {"item": "laptop", "count": 1, "position": "on the table", "size": "0.34 x 0.24 x 0.02 m"},
                              {"item": "lamp", "count": 1, "position": "", "size": "0.24 x 0.24 x 0.5 m"}],
                "tools": ["object.create", "object.transform", "material.recipe", "camera.create", "scene.save"],
                "missing": [], "save": {"wanted": True, "filename": "desk_test.blend"}})}]})
        if "You arrange objects in a Blender scene" in system:
            seen["place"] += 1
            text = body["messages"][-1]["content"]
            table = _re.search(r"- table \(table\): size \[([-\d., ]+)\], bottom centre now \[([-\d., ]+)\]", text)
            size = [float(v) for v in table.group(1).split(",")]
            base = [float(v) for v in table.group(2).split(",")]
            top = base[2] + size[2]
            places = [{"thing": "book_1", "location": [base[0] - 0.35, base[1], top], "why": "on the table"},
                      {"thing": "book_2", "location": [base[0] - 0.35, base[1] + 0.22, top], "why": "on the table"},
                      {"thing": "laptop", "location": [base[0] + 0.2, base[1] - 0.05, top], "why": "on the table"},
                      {"thing": "lamp", "location": [base[0] + 0.95, base[1], 0.0], "why": "beside the table"}]
            return _Reply({"content": [{"type": "text", "text": json.dumps({"placements": places})}]})
        if body.get("tools"):
            seen["tools_sent"] = max(seen["tools_sent"], len(body["tools"]))
            if not state["built"]:
                state["built"] = True
                seen["build_turns"] += 1
                return _Reply({"content": build, "stop_reason": "tool_use"})
        return _Reply({"content": [{"type": "text", "text": "Built the table, two books, the laptop and the lamp."}]})

    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    addon.reset_providers()
    try:
        with mock.patch.object(net, "urlopen", fake_urlopen):
            controller = addon.get_copilot_controller(provider_name="claude")
            started = time.time()
            result = controller.submit("create a table with two books and a laptop, and a lamp, save it as desk_test")
        print(f"  checklist run: {time.time() - started:.0f}s; {seen}")
        check(seen["plan"] == 1, "the AI wrote the checklist first (1 planner call)")
        plan_msgs = [m.content for m in controller.session.get_messages() if "PLAN - what will be built" in (m.content or "")]
        check(bool(plan_msgs) and "book" in plan_msgs[0] and "x2" in plan_msgs[0], "checklist shown before building")
        check(0 < seen["tools_sent"] <= 30, f"only the planner's tools were sent ({seen['tools_sent']} of 57)")
        check(seen["place"] == 1, "the AI decided the places")
        top = bpy.data.objects["table_top"]
        top_z = max((top.matrix_world @ v.co).z for v in top.data.vertices)
        for name in ("book_1", "book_2", "laptop"):
            obj = bpy.data.objects[name]
            bottom = min((obj.matrix_world @ v.co).z for v in obj.data.vertices)
            check(abs(bottom - top_z) < 0.003, f"{name} rests ON the table (bottom {bottom:.3f} = top {top_z:.3f})")
        if render:
            check(seen["vision"] >= 1 and seen["images"] >= 9 + 3, f"every angle + zoom-ins ({seen['images']} images)")
            check(seen.get("checklist_sent") and seen["zoom"] >= 3, "checklist + close-ups went to the reviewer")
        saved = os.path.join(WORK, "BlenderAIAgent", "scenes", "desk_test.blend")
        check(os.path.isfile(saved) and os.path.getsize(saved) > 10000, f"file saved ({saved})")
        check("Saved the final scene" in (result.reply_text or "") and "checked on disk" in (result.reply_text or ""),
              "the final, placed scene was saved again and verified")
        check(result.success, "run finished as completed: " + (result.reply_text or "").splitlines()[0][:80])
        check("AI use:" in (result.reply_text or "") and "request(s)" in (result.reply_text or ""),
              "the reply says how many AI requests / tokens the run used")
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        addon.reset_providers()


def stop_run(addon) -> None:
    """Stop works at once: in the middle of the check renders, and while the AI is still thinking."""
    import threading
    from unittest import mock

    from blender_ai_agent import net
    from blender_ai_agent.bridge.main_thread_dispatch import drain_dispatch_queue
    from blender_ai_agent.copilot import activity

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.ops.mesh.primitive_cube_add()
    cube = bpy.context.active_object.name
    folder = os.path.join(WORK, "stop_renders")
    activity.begin_run()
    out = {}

    def renders():
        try:
            addon.get_bridge().render_views([cube], ["front", "back", "left", "right", "top", "low", "wide"], 640,
                                            folder, "s")
            out["result"] = "all"
        except RuntimeError as exc:
            out["result"] = str(exc)
    worker = threading.Thread(target=renders)
    worker.start()
    started = time.time()
    while worker.is_alive():
        drain_dispatch_queue()
        time.sleep(0.02)
        if time.time() - started > 0.3 and not activity.should_stop():
            activity.abandon()                                   # the Stop button
    made = len([f for f in os.listdir(folder) if f.startswith("s_")]) if os.path.isdir(folder) else 0
    check("Stopped" in out.get("result", "") and made < 7, f"Stop ends the check renders ({made} of 7 made)")
    check(bpy.context.scene.camera is None or not bpy.context.scene.camera.name.startswith("_aiagent"),
          "the scene is restored after a stopped render")
    activity.end_run()
    activity.run_thread_ended()

    def hang(request, timeout=None):
        time.sleep(30)
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    addon.reset_providers()
    try:
        with mock.patch.object(net, "_urlopen", hang):
            controller = addon.get_copilot_controller(provider_name="claude")
            activity.begin_run()
            done = {}
            thread = threading.Thread(target=lambda: done.update(r=controller.submit("make a red cube")))
            thread.start()
            time.sleep(1.0)
            stop_at = time.time()
            activity.abandon()
            controller.cancel()
            while thread.is_alive():
                drain_dispatch_queue()
                time.sleep(0.02)
            check(time.time() - stop_at < 2.0, f"Stop ends the wait for the AI ({time.time() - stop_at:.1f}s)")
            check([o.name for o in bpy.data.objects] == [cube], "nothing is built after Stop")
    finally:
        activity.end_run()
        activity.run_thread_ended()
        os.environ.pop("ANTHROPIC_API_KEY", None)
        addon.reset_providers()


def resume_run(addon) -> None:
    """Stop part-way with Claude, pick OpenAI, press Continue: the plan is reused (no new planning request), the table
    built before is kept (not built twice), OpenAI (Responses API, function tools) builds the missing books."""
    import threading
    from unittest import mock

    from blender_ai_agent import net
    from blender_ai_agent.bridge.main_thread_dispatch import drain_dispatch_queue
    from blender_ai_agent.copilot import activity, resume

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    with open(os.path.join(WORK, "BlenderAIAgent", "autoverify.json"), "w") as handle:
        json.dump({"mode": "console", "max_rounds": 1}, handle)
    seen = {"claude_plan": 0, "openai_plan": 0, "openai_urls": set(), "temperature": False, "tool_names": []}
    claude_turns = {"n": 0}

    def ctool(tool_name, **args):
        return {"type": "tool_use", "id": f"t{time.time_ns()}", "name": tool_name.replace(".", "__"), "input": args}

    def claude(request, timeout=None):
        body = json.loads(request.data or b"{}")
        system = body.get("system") or ""
        if "You are the planner of a Blender AI copilot" in system:
            seen["claude_plan"] += 1
            return _Reply({"content": [{"type": "text", "text": json.dumps({
                "kind": "new", "checklist": [{"item": "table", "count": 1, "position": ""},
                                             {"item": "book", "count": 2, "position": "on the table"}],
                "tools": ["object.create", "object.transform"], "missing": [], "save": {"wanted": False}})}]})
        if body.get("tools"):
            claude_turns["n"] += 1
            if claude_turns["n"] == 1:
                return _Reply({"content": [ctool("object.create", name="table_top", primitive="CUBE",
                                                 location=[0, 0, 0.75]),
                                           ctool("object.transform", name="table_top", scale=[0.6, 0.4, 0.025])],
                               "stop_reason": "tool_use"})
            time.sleep(30)                                   # Claude thinks long ... the user presses Stop
        return _Reply({"content": [{"type": "text", "text": "ok"}]})

    def openai(request, timeout=None):
        seen["openai_urls"].add(request.full_url)
        body = json.loads(request.data or b"{}")
        seen["temperature"] = seen["temperature"] or "temperature" in body
        if "You are the planner of a Blender AI copilot" in (body.get("instructions") or ""):
            seen["openai_plan"] += 1
        if "You arrange objects" in (body.get("instructions") or ""):
            return _Reply({"status": "completed", "output": [{"type": "message", "content": [
                {"type": "output_text", "text": json.dumps({"placements": []})}]}]})
        if body.get("tools"):
            seen["tool_names"] = [t["name"] for t in body["tools"]]
            text = json.dumps(body["input"])
            if "book_1" not in text:
                return _Reply({"status": "completed", "usage": {"input_tokens": 5000, "output_tokens": 300}, "output": [
                    {"type": "reasoning", "summary": []},
                    {"type": "function_call", "call_id": "a", "name": "object__create",
                     "arguments": json.dumps({"name": "book_1", "primitive": "CUBE", "location": [-0.2, 0, 0.79]})},
                    {"type": "function_call", "call_id": "b", "name": "object__create",
                     "arguments": json.dumps({"name": "book_2", "primitive": "CUBE", "location": [0.2, 0, 0.79]})}]})
        return _Reply({"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": "The table was there; I added the two books."}]}]})

    def route(request, timeout=None):
        return openai(request, timeout) if "openai.com" in request.full_url else claude(request, timeout)

    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    os.environ["OPENAI_API_KEY"] = "test-key"
    addon.reset_providers()
    try:
        with mock.patch.object(net, "_urlopen", route):
            controller = addon.get_copilot_controller(provider_name="claude")
            activity.begin_run()
            thread = threading.Thread(target=lambda: controller.submit("create a table with two books"))
            thread.start()
            waited = time.time()
            while claude_turns["n"] < 2 and thread.is_alive() and time.time() - waited < 60:
                drain_dispatch_queue()
                time.sleep(0.02)
            print(f"  (claude turns before Stop: {claude_turns['n']})")
            activity.abandon()                                # Stop while Claude is thinking
            controller.cancel()
            while thread.is_alive():
                drain_dispatch_queue()
                time.sleep(0.02)
            activity.end_run()
            activity.run_thread_ended()
            info = resume.pending()
            check(bool(info) and info["why"] == "stopped by the user", f"the stopped run is remembered ({info})")
            check("table_top" in bpy.data.objects, "what Claude built before Stop stays")

            controller = addon.get_copilot_controller(provider_name="openai")          # the user picks OpenAI
            activity.begin_run()
            done = {}
            thread = threading.Thread(target=lambda: done.update(r=controller.submit(resume.prompt())))
            thread.start()
            while thread.is_alive():
                drain_dispatch_queue()
                time.sleep(0.02)
            activity.end_run()
            result = done["r"]
        check(result.success, "Continue with OpenAI finished: " + (result.reply_text or "").splitlines()[0][:70])
        check(seen["claude_plan"] == 1 and seen["openai_plan"] == 0, "the plan was reused - no second planning request")
        names = sorted(o.name for o in bpy.data.objects)
        check(names == ["book_1", "book_2", "table_top"], f"only the missing books were built, nothing twice ({names})")
        check(seen["openai_urls"] == {"https://api.openai.com/v1/responses"}, "OpenAI is called on the Responses API")
        check(not seen["temperature"] and "object__create" in seen["tool_names"], "no temperature; tool names mapped")
        check(resume.pending() is None, "nothing left to continue")
    finally:
        activity.end_run()
        activity.run_thread_ended()
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("OPENAI_API_KEY", None)
        addon.reset_providers()


def skill_run(addon) -> None:
    """'make a campfire' is built by the library skill alone: no AI request at all, at once."""
    from unittest import mock

    from blender_ai_agent import net

    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    with open(os.path.join(WORK, "BlenderAIAgent", "autoverify.json"), "w") as handle:
        json.dump({"mode": "full", "resolution": 128, "max_rounds": 1}, handle)
    asked = []
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    addon.reset_providers()
    try:
        with mock.patch.object(net, "_urlopen", lambda request, timeout=None: asked.append(request) or _Reply({})):
            controller = addon.get_copilot_controller(provider_name="claude")
            started = time.time()
            result = controller.submit("make a campfire")
        check(result.success and "campfire_embers" in bpy.data.objects, "the campfire was built")
        check(not asked, f"no AI request for a ready-made model ({len(asked)} sent)")
        check(time.time() - started < 10, f"built at once ({time.time() - started:.1f}s)")
    finally:
        os.environ.pop("ANTHROPIC_API_KEY", None)
        addon.reset_providers()


if __name__ == "__main__":
    sys.exit(main(render="--render" in sys.argv))
