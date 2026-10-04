from . import _bpy_stub  # noqa: F401

import base64
import json
import os
import re
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from blender_ai_agent.agent import self_correct as sc
from blender_ai_agent.agent.build_script import function_name, validate_script
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.skills.builtins.iterative_build import IterativeBuildSkill
from blender_ai_agent.skills.registry import SkillRegistry
from blender_ai_agent.tools.base import Permission, Tool, ToolResult
from blender_ai_agent.tools.iterate_tools import BuildIterateInput, BuildIterateTool
from blender_ai_agent.tools.mesh_advanced_tools import MeshLatheTool, MeshSdfTool
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.render_views import VIEW_DIRECTIONS, camera_pose, normalize_view
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeObject
from .fakes_ext import FakeBridge

PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
       b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82")


# ------------------------------------------------------------------ tools for the registry (real mesh.sdf + small stand-ins)
class _Base(Tool):
    def __init__(self, bridge):
        self._bridge = bridge


def _simple_tool(tool_name, fields, handler, permission=Permission.SAFE_WRITE, description=""):
    import dataclasses
    spec = [(n, t, dataclasses.field(default_factory=d) if callable(d) else dataclasses.field(default=d)) for n, t, d in fields]
    model = dataclasses.make_dataclass(tool_name.replace(".", "_").title() + "Input", spec)

    def run(self, v):
        return handler(self._bridge, v)

    return type("T_" + tool_name.replace(".", "_"), (_Base,), {
        "name": tool_name, "input_model": model, "permission": permission,
        "description": description or f"{tool_name} (test stand-in)", "run": run})


def _create(bridge, v):
    obj = FakeObject(name=v.name)
    obj.location = list(v.location)
    existing = {o.name for o in bridge._objects}
    n, final = 0, v.name
    while final in existing:
        n += 1
        final = f"{v.name}.{n:03d}"
    obj.name = final
    obj.fake_bbox = {"min": [-0.5, -0.5, 0.0], "max": [0.5, 0.5, 1.0]}
    bridge._objects.append(obj)
    return ToolResult.ok({"name": obj.name, "location": list(v.location)})


def _delete(bridge, v):
    before = len(bridge._objects)
    bridge._objects = [o for o in bridge._objects if o.name != v.name]
    return ToolResult.ok({"deleted": before - len(bridge._objects)}) if before != len(bridge._objects) else ToolResult.fail(f"no object {v.name}")


def _transform(bridge, v):
    obj = bridge.get_object(v.name)
    if obj is None:
        return ToolResult.fail(f"no object {v.name}")
    if v.scale is not None:
        obj.scale = list(v.scale)
    return ToolResult.ok({"name": v.name})


def _material(bridge, v):
    return ToolResult.ok({"name": v.name})


def _assign(bridge, v):
    if bridge.get_object(v.object_name) is None:
        return ToolResult.fail(f"no object {v.object_name}")
    return ToolResult.ok({"object": v.object_name})


ObjectCreate = _simple_tool("object.create", [("name", str, "Cube"), ("primitive", str, "CUBE"), ("location", list, lambda: [0.0, 0.0, 0.0])], _create,
                            description="Creates a primitive object (CUBE, SPHERE, CYLINDER, CONE, PLANE).")
ObjectDelete = _simple_tool("object.delete", [("name", str, "")], _delete, Permission.DESTRUCTIVE, "Deletes an object.")
ObjectTransform = _simple_tool("object.transform", [("name", str, ""), ("scale", object, None)], _transform)
MaterialCreate = _simple_tool("material.create", [("name", str, "Mat"), ("color", object, None)], _material)
MaterialAssign = _simple_tool("material.assign", [("object_name", str, ""), ("material_name", str, "")], _assign)


def make_stack(bridge):
    registry = ToolRegistry()
    for tool in (ObjectCreate(bridge), ObjectDelete(bridge), ObjectTransform(bridge), MaterialCreate(bridge), MaterialAssign(bridge),
                 MeshSdfTool(bridge), MeshLatheTool(bridge), SceneInspectTool(SceneInspector(bridge))):
        registry.register(tool)
    return registry, ToolCaller(registry)


class SceneBridge(FakeBridge):
    """mesh.sdf ke liye create_mesh + scene.inspect ke liye object fields."""

    def create_mesh(self, name, vertices, faces, location=None, rotation=None, scale=None, shade_smooth=False):
        obj = super().create_mesh(name, vertices, faces, location, rotation, scale, shade_smooth)
        xs = [v[0] for v in vertices]; ys = [v[1] for v in vertices]; zs = [v[2] for v in vertices]
        obj.fake_bbox = {"min": [min(xs), min(ys), min(zs)], "max": [max(xs), max(ys), max(zs)]}
        return obj


GOOD_SCRIPT = '''
material_create(name="Paint", color=[0.7, 0.1, 0.1])
body = object_create(name="Thing_body", primitive="CUBE", location=[0, 0, 0.5])
object_transform(name=body["name"], scale=[1, 2, 0.5])
material_assign(object_name=body["name"], material_name="Paint")
for i in range(4):
    w = object_create(name=f"Thing_wheel{i}", primitive="CYLINDER", location=[i, 0, 0.3])
'''
SCRIPT_V2 = GOOD_SCRIPT + '\nlamp = object_create(name="Thing_lamp", primitive="SPHERE", location=[0, 2, 1])\n'
BAD_TOOL_SCRIPT = 'object_create(name="Half", primitive="CUBE")\nmesh_sdf(name="Boom", shapes=[])\n'


def fenced(code):
    return f"Here you go:\n```python\n{code.strip()}\n```\n"


def critique(score, problems=(), keep=(), summary="ok"):
    return json.dumps({"score": score, "matches_prompt": score >= 7, "summary": summary, "keep": list(keep),
                       "problems": [{"severity": "high", "where": "body", "issue": p, "fix": "move it"} for p in problems]})


class ScriptedGemini(BaseHTTPRequestHandler):
    """Writer/fixer aur critic ke jawab list se; har request record hoti hai."""

    def log_message(self, *a):
        pass

    def _send(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body)))
        self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        self.server.requests.append({"method": "GET", "path": self.path})
        self._send(200, {"models": [
            {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.5-flash-lite", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.6-flash-image", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-3.6-pro", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-embedding", "supportedGenerationMethods": ["embedContent"]}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        model = self.path.split("/models/")[1].split(":")[0]
        system = body["systemInstruction"]["parts"][0]["text"]
        role = "critic" if system.startswith("You are a strict 3D art reviewer") else "writer"
        images = sum(1 for part in body["contents"][0]["parts"] if "inline_data" in part)
        texts = " ".join(part.get("text", "") for part in body["contents"][0]["parts"])
        self.server.requests.append({"method": "POST", "model": model, "role": role, "images": images, "text": texts, "system": system,
                                     "json_mode": body["generationConfig"].get("responseMimeType") == "application/json",
                                     "key": self.headers.get("x-goog-api-key")})
        queue = self.server.queues[role]
        fail = self.server.fail_models.get(model)
        if fail:
            return self._send(fail, {"error": {"message": "limit"}})
        if not queue:
            return self._send(500, {"error": {"message": f"no scripted {role} answer left"}})
        self._send(200, {"candidates": [{"content": {"parts": [{"text": queue.pop(0)}]}}]})


class LoopCase(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ScriptedGemini)
        self.server.requests, self.server.queues, self.server.fail_models = [], {"writer": [], "critic": []}, {}
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1beta"
        self.bridge = SceneBridge()
        self.registry, self.caller = make_stack(self.bridge)
        self.cfg = sc.BuilderConfig(api_key="test-key-123", api_base=self.url, request_timeout_s=10, max_iterations=3, target_score=8.0,
                                    resolution=64)

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.tmp.cleanup()

    def builder(self, **kw):
        cfg = sc.BuilderConfig(**{**self.cfg.__dict__, **kw})
        return sc.SelfCorrectingBuilder(self.caller, self.registry, self.bridge, sc.GeminiClient(cfg), cfg)

    def writer(self, *scripts):
        self.server.queues["writer"].extend(fenced(s) if not s.startswith("Here") else s for s in scripts)

    def critic(self, *answers):
        self.server.queues["critic"].extend(answers)

    def names(self):
        return sorted(o.name for o in self.bridge._objects)

    def posts(self, role=None):
        return [r for r in self.server.requests if r["method"] == "POST" and (role is None or r["role"] == role)]

    def build(self, request="make a thing", **kw):
        return self.builder(**kw).build(request, out_dir=os.path.join(self.tmp.name, "out"))


class TestHelpers(unittest.TestCase):

    def test_extract_script(self):
        self.assertEqual(sc.extract_script("hi\n```python\nx = 1\n```\nbye"), "x = 1")
        self.assertEqual(sc.extract_script("```py\na = 1\n```\n```python\nb = 2\nc = 3\n```"), "b = 2\nc = 3")
        self.assertEqual(sc.extract_script("x = 5"), "x = 5")
        self.assertEqual(sc.extract_script(""), "")

    def test_parse_critique_is_forgiving(self):
        good = sc.parse_critique(critique(7.5, ["wheel floats"], ["colour"], "close"))
        self.assertEqual((good.score, good.matches, good.summary, good.keep), (7.5, True, "close", ["colour"]))
        self.assertEqual(good.problems[0]["issue"], "wheel floats")
        wrapped = sc.parse_critique("Sure!\n```json\n" + critique(4) + "\n```")
        self.assertEqual(wrapped.score, 4)
        for bad in ("", "no json at all", "[1,2]", "{broken"):
            parsed = sc.parse_critique(bad)
            self.assertFalse(parsed.raw_ok, bad)
            self.assertEqual(parsed.score, 0.0)
        self.assertEqual(sc.parse_critique('{"score": 99}').score, 10.0)
        self.assertEqual(sc.parse_critique('{"score": "x"}').score, 0.0)
        many = sc.parse_critique(json.dumps({"score": 5, "problems": [f"p{i}" for i in range(20)]}))
        self.assertEqual(len(many.problems), 6)
        self.assertEqual(many.problems[0]["severity"], "medium")

    def test_config_from_file_and_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "builder.json")
            with open(path, "w") as handle:
                json.dump({"max_iterations": 99, "target_score": "7", "views": ["front", "top"], "model": "my-model", "unknown": 1}, handle)
            saved = {k: os.environ.get(k) for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
            os.environ["GEMINI_API_KEY"] = "env-key"; os.environ.pop("GOOGLE_API_KEY", None)
            try:
                cfg = sc.load_builder_config(path)
            finally:
                for k, v in saved.items():
                    os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
            self.assertEqual((cfg.api_key, cfg.max_iterations, cfg.target_score, cfg.views, cfg.model), ("env-key", 6, 7.0, ("front", "top"), "my-model"))
            self.assertTrue(sc.load_builder_config(os.path.join(tmp, "missing.json")).max_iterations >= 1)

    def test_camera_poses(self):
        low, high = (-2.25, -0.97, 0.0), (2.25, 0.97, 1.55)
        radius = 0.5 * ((4.5 ** 2 + 1.94 ** 2 + 1.55 ** 2) ** 0.5)
        for view in VIEW_DIRECTIONS:
            pose = camera_pose(low, high, view)
            self.assertGreater(pose["distance"], radius)                     # poori cheez frame mein
            self.assertEqual(pose["target"], [0.0, 0.0, 0.775])
        self.assertLess(camera_pose(low, high, "front")["location"][1], 0)   # front = -Y
        self.assertGreater(camera_pose(low, high, "right")["location"][0], 0)
        self.assertGreater(camera_pose(low, high, "top")["location"][2], camera_pose(low, high, "front")["location"][2])
        self.assertEqual(normalize_view("3/4"), "three_quarter")
        self.assertEqual(normalize_view("Side"), "right")
        with self.assertRaises(ValueError):
            normalize_view("sideways")

    def test_the_writer_prompt_lists_tools_and_its_examples_are_valid_scripts(self):
        bridge = SceneBridge()
        registry, _ = make_stack(bridge)
        names = [n for n in registry.list_tools() if n not in sc.EXCLUDED_TOOLS]
        listing = sc.describe_tools(registry, names)
        self.assertIn("mesh_sdf(", listing)
        self.assertIn("object_create(name='Cube'", listing)
        self.assertNotIn("scene_inspect", listing)
        examples = re.findall(r"```python\n(.*?)```", sc.WRITER_SYSTEM, re.DOTALL)
        self.assertEqual(len(examples), 2)
        functions = {function_name(n) for n in names} | {"material_modify", "mesh_lathe", "mesh_prism", "character_create", "curve_create"}
        for example in examples:
            validate_script(example, functions)                                # syntax + sandbox rules ke hisaab se sahi


class TestPromptExamples(LoopCase):
    """Prompt ke dono example scripts asli mesh.sdf ke saath poore chalte hain (galat argument ya galat orientation pakadne ke liye)."""

    def test_both_examples_run_and_the_car_is_a_car(self):
        from blender_ai_agent.agent.build_script import run_script
        from blender_ai_agent.agent.models import ToolCall
        MaterialModify = _simple_tool("material.modify", [("name", str, ""), ("metallic", object, None), ("roughness", object, None)], _material)
        self.registry.register(MaterialModify(self.bridge))
        names = [n for n in self.registry.list_tools() if n not in sc.EXCLUDED_TOOLS]
        examples = re.findall(r"```python\n(.*?)```", sc.WRITER_SYSTEM, re.DOTALL)
        for source in examples:
            result = run_script(source, lambda tool, kwargs: self.caller.call(ToolCall(tool_name=tool, arguments=kwargs)), names)
            self.assertTrue(result.ok, result.error)
        by_name = {o.name: o for o in self.bridge._objects}
        self.assertEqual(sorted(n for n in by_name if n.startswith("Table_")), ["Table_leg0", "Table_leg1", "Table_leg2", "Table_leg3", "Table_top"])
        body = by_name["Car_body"]
        ys = [v[1] for v in body.mesh_vertices]
        zs = [v[2] for v in body.mesh_vertices]
        self.assertAlmostEqual(max(ys) - min(ys), 4.5, delta=0.1)                 # lambai
        self.assertLess(max(zs), 1.7)

        def closed(obj):                                                            # har edge ke theek 2 faces => band (koi chhed nahi)
            count = {}
            for face in obj.mesh_faces:
                for k in range(len(face)):
                    edge = tuple(sorted((face[k], face[(k + 1) % len(face)])))
                    count[edge] = count.get(edge, 0) + 1
            return all(c == 2 for c in count.values())
        for i in range(4):
            tyre, hub = by_name[f"Car_tyre{i}"], by_name[f"Car_hub{i}"]
            for part in (tyre, hub):
                self.assertTrue(closed(part), f"{part.name} has holes")
            tx = [v[0] for v in tyre.mesh_vertices]
            tz = [v[2] for v in tyre.mesh_vertices]
            self.assertAlmostEqual(max(tz) - min(tz), 0.22, delta=0.02)               # lathe axis Z: chaudai (rotation [0,90,0] se X banti hai)
            self.assertAlmostEqual(max(tx) - min(tx), 0.69, delta=0.03)               # diameter
            rotation = getattr(tyre, "rotation", None) or tyre.rotation_euler
            self.assertTrue(abs(rotation[1] - 90.0) < 1e-6 or abs(rotation[1] - 1.5707963) < 1e-5, rotation)    # axis Z -> X
            self.assertAlmostEqual(tyre.location[2], 0.345)                            # zameen par khada


class TestTheLoop(LoopCase):

    def test_first_try_good_stops_immediately(self):
        self.writer(GOOD_SCRIPT)
        self.critic(critique(8.5, keep=["proportions"], summary="clearly a thing"))
        report = self.build()
        self.assertTrue(report.success and report.reached_target)
        self.assertEqual((report.best_score, report.best_iteration, len(report.iterations)), (8.5, 1, 1))
        self.assertEqual(report.llm_calls, 2)
        self.assertEqual(self.names(), ["Thing_body", "Thing_wheel0", "Thing_wheel1", "Thing_wheel2", "Thing_wheel3"])
        self.assertEqual(report.objects, self.names())
        self.assertEqual(len(report.images), 4)

    def test_requests_carry_the_key_in_a_header_and_the_images_to_the_critic(self):
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        self.build("make a thing with 4 wheels")
        self.assertTrue(all(p["key"] == "test-key-123" for p in self.posts()))
        writer, critic = self.posts("writer")[0], self.posts("critic")[0]
        self.assertIn("make a thing with 4 wheels", writer["text"])
        self.assertIn("ANCHOR", writer["text"])
        self.assertIn("mesh_sdf(", writer["system"])
        self.assertEqual(critic["images"], 4)                                  # front, right, top, three_quarter
        self.assertTrue(critic["json_mode"])
        self.assertIn("make a thing with 4 wheels", critic["text"])
        self.assertFalse(writer["json_mode"])

    def test_critique_feeds_the_next_script_and_the_best_version_wins(self):
        self.writer(GOOD_SCRIPT, SCRIPT_V2)
        self.critic(critique(5, ["no lamp on the front"], ["wheels"], "needs a lamp"), critique(8.2, summary="good now"))
        report = self.build()
        self.assertTrue(report.reached_target)
        self.assertEqual((report.best_iteration, report.best_score, len(report.iterations)), (2, 8.2, 2))
        self.assertIn("Thing_lamp", self.names())
        fixer = self.posts("writer")[1]
        self.assertIn("no lamp on the front", fixer["text"])                  # critique wapas gayi
        self.assertIn("YOUR PREVIOUS SCRIPT", fixer["text"])
        self.assertIn("Thing_wheel", fixer["text"])                            # purani script bhi
        self.assertIn("SCORES SO FAR: 5", fixer["text"])
        self.assertEqual(len(self.names()), 6)                                 # purana hata kar naya: duplicate nahi

    def test_a_worse_iteration_is_rolled_back_and_the_best_is_rebuilt(self):
        self.writer(SCRIPT_V2, GOOD_SCRIPT, GOOD_SCRIPT)
        self.critic(critique(6.5), critique(4.0, ["worse"]), critique(5.0))
        report = self.build()
        self.assertFalse(report.reached_target)
        self.assertEqual((report.best_iteration, report.best_score), (1, 6.5))
        self.assertTrue(report.success)
        self.assertIn("Thing_lamp", self.names())                              # iteration 1 wapas bana
        self.assertEqual(len(self.names()), 6)
        self.assertIn("best score 6.5", report.stopped_reason)

    def test_script_errors_are_fed_back_with_line_and_reason(self):
        self.writer(BAD_TOOL_SCRIPT, GOOD_SCRIPT)
        self.critic(critique(8.1))
        report = self.build()
        self.assertTrue(report.success)
        first, second = report.iterations
        self.assertFalse(first.run_ok if first.score == 0 and first.run_error else True)
        self.assertIn("line 2", first.run_error)
        self.assertIn("mesh.sdf failed", first.run_error)
        self.assertIn("RUN ERROR: line 2", self.posts("writer")[1]["text"])
        self.assertEqual(self.names(), ["Thing_body", "Thing_wheel0", "Thing_wheel1", "Thing_wheel2", "Thing_wheel3"])     # 'Half' hat gaya
        self.assertEqual(len(self.posts("critic")), 1)                         # error wali iteration ka render nahi

    def test_everything_failing_leaves_the_scene_untouched(self):
        self.writer(BAD_TOOL_SCRIPT, BAD_TOOL_SCRIPT, BAD_TOOL_SCRIPT)
        report = self.build()
        self.assertFalse(report.success)
        self.assertEqual(self.names(), [])
        self.assertEqual(report.objects, [])
        self.assertTrue(all(i.run_error for i in report.iterations))

    def test_dangerous_scripts_are_rejected_and_fixed_before_running(self):
        self.writer("import os\nos.system('x')", "x = open('f')", GOOD_SCRIPT)
        self.critic(critique(9))
        report = self.build()
        self.assertTrue(report.success)
        retry = self.posts("writer")[1]["text"]
        self.assertIn("rejected before running", retry)
        self.assertIn("import", retry)
        self.assertEqual(len(report.iterations), 1)                            # retries ek hi iteration ke andar

    def test_script_that_stays_dangerous_is_reported_not_run(self):
        self.writer("import os", "import os", "import os", "import os")
        report = self.build(max_iterations=1)
        self.assertFalse(report.success)
        self.assertIn("script rejected", report.iterations[0].run_error)
        self.assertEqual(self.names(), [])

    def test_cannot_delete_objects_that_existed_before(self):
        self.bridge._objects.append(FakeObject(name="UserCube"))
        self.writer('object_create(name="Mine", primitive="CUBE")\nobject_delete(name="UserCube")', GOOD_SCRIPT)
        self.critic(critique(8.5))
        report = self.build()
        self.assertIn("UserCube", self.names())                                # user ka object bacha
        self.assertIn("existed before", report.iterations[0].run_error)
        self.assertTrue(report.success)

    def test_deleting_its_own_object_is_fine_and_user_objects_are_never_in_the_report(self):
        self.bridge._objects.append(FakeObject(name="UserCube"))
        self.writer('t = object_create(name="Temp", primitive="CUBE")\nobject_delete(name=t["name"])\nobject_create(name="Keep", primitive="CUBE")')
        self.critic(critique(9))
        report = self.build()
        self.assertEqual(report.objects, ["Keep"])
        self.assertEqual(self.names(), ["Keep", "UserCube"])

    def test_quota_after_a_good_iteration_returns_the_best_so_far(self):
        self.writer(GOOD_SCRIPT)
        self.critic(critique(6, ["thin"]))
        self.server.fail_models = {"gemini-3.6-flash": 429, "gemini-3.5-flash-lite": 429}
        builder = self.builder()
        first = builder.build("make a thing", out_dir=os.path.join(self.tmp.name, "out1"))                # sab 429 -> kuch nahi
        self.assertFalse(first.success)
        self.assertIn("429", first.stopped_reason)
        self.server.fail_models = {}
        self.writer(GOOD_SCRIPT, SCRIPT_V2)
        self.critic(critique(6, ["thin"]))
        builder = self.builder()
        original = builder._critique
        calls = {"n": 0}

        def flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise sc.BuilderError("quota", "Gemini ka quota khatam ho gaya (429).")
            return original(*a, **k)
        builder._critique = flaky
        report = builder.build("make a thing", out_dir=os.path.join(self.tmp.name, "out2"))
        self.assertTrue(report.success)
        self.assertEqual(report.best_iteration, 1)                              # iteration 1 (score 6) bacha
        self.assertIn("429", report.stopped_reason)
        self.assertEqual(len(self.names()), 5)

    def test_fallback_model_is_used_when_the_first_is_rate_limited(self):
        self.server.fail_models = {"gemini-3.6-flash": 429}
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        report = self.build()
        self.assertTrue(report.success)
        models = [p["model"] for p in self.posts()]
        self.assertEqual(models, ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash-lite"])   # ek baar 429, phir sticky fallback
        self.assertEqual(self.server.requests[0]["method"], "GET")              # model discovery

    def test_model_discovery_picks_the_newest_flash_and_skips_image_pro_embedding(self):
        client = sc.GeminiClient(self.cfg)
        self.assertEqual(client.models(), ["gemini-3.6-flash", "gemini-3.5-flash-lite"])

    def test_render_failure_still_keeps_what_was_built(self):
        self.bridge.render_fails = True
        self.writer(GOOD_SCRIPT)
        report = self.build()
        self.assertTrue(report.success)
        self.assertIn("not reviewed", report.iterations[0].summary)
        self.assertEqual(len(self.names()), 5)

    def test_unreadable_critique_still_lets_the_loop_continue(self):
        self.writer(GOOD_SCRIPT, SCRIPT_V2)
        self.critic("I think it looks nice!", critique(8.4))
        report = self.build()
        self.assertEqual(report.best_iteration, 2)
        self.assertIn("unreadable", self.posts("writer")[1]["text"])

    def test_artifacts_are_saved(self):
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        report = self.build()
        folder = report.folder
        self.assertTrue(os.path.isfile(os.path.join(folder, "iteration_1.py")))
        self.assertTrue(os.path.isfile(os.path.join(folder, "report.json")))
        self.assertTrue(all(os.path.isfile(p) for p in report.images))
        with open(os.path.join(folder, "report.json")) as handle:
            saved = json.load(handle)
        self.assertEqual(saved["best_score"], 9)

    def test_free_spot_avoids_existing_objects(self):
        first = FakeObject(name="Tent"); first.location = [0.0, 0.0, 0.0]
        self.bridge._objects.append(first)
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        report = self.build()
        self.assertNotEqual(report.anchor[:2], [0.0, 0.0])
        self.assertIn(f"x={report.anchor[0]}", self.posts("writer")[0]["text"])
        self.assertIn("Tent", self.posts("writer")[0]["text"])

    def test_placement_overlap_is_caught_even_when_the_reviewer_is_happy(self):
        tent = FakeObject(name="Tent")
        tent.location = [0.0, 0.0, 0.0]
        self.bridge._objects.append(tent)
        clash = 'object_create(name="Thing_body", primitive="CUBE", location=[0.3, 0.2, 0.5])\nobject_create(name="Thing_extra", primitive="CUBE", location=[0.3, 0.2, 0.5])'
        clear = 'object_create(name="Thing_body", primitive="CUBE", location=[6, 6, 0.5])\nobject_create(name="Thing_extra", primitive="CUBE", location=[6, 6, 0.5])'
        self.writer(clash, clear)
        self.critic(critique(9.5, summary="perfect car"), critique(9.0))
        report = self.build()
        first, second = report.iterations
        self.assertLess(first.score, 8)                                              # 9.5 ke bawajood overlap ne score gira diya
        self.assertIn("overlaps the existing object 'Tent'", first.problems[0]["issue"])
        self.assertEqual(first.problems[0]["where"], "placement")
        self.assertIn("overlaps the existing object 'Tent'", self.posts("writer")[1]["text"])     # fixer ko physical fact mila
        self.assertTrue(report.reached_target)
        self.assertEqual(report.best_iteration, 2)

    def test_ground_planes_and_far_objects_are_not_overlaps(self):
        floor = FakeObject(name="Ground")
        floor.location = [0.0, 0.0, 0.0]
        floor.fake_bbox = {"min": [-50.0, -50.0, -0.01], "max": [50.0, 50.0, 0.01]}
        far = FakeObject(name="FarRock")
        far.location = [40.0, 0.0, 0.0]
        self.bridge._objects.extend([floor, far])
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        report = self.build()
        self.assertTrue(report.reached_target)
        self.assertEqual(report.iterations[0].score, 9)

    def test_vehicles_get_more_room_and_the_writer_sees_where_things_are(self):
        near = FakeObject(name="Girl")
        near.location = [4.0, 0.0, 0.0]
        self.bridge._objects.append(near)
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        car = self.builder().build("make a realistic sports car", out_dir=os.path.join(self.tmp.name, "c"))
        self.assertGreaterEqual(((car.anchor[0] - 4.0) ** 2 + car.anchor[1] ** 2) ** 0.5, 8.0)           # gaadi: 8 m
        self.assertIn("Girl@(4.0,0.0)", self.posts("writer")[0]["text"])
        self.assertIn("at least 1 m", self.posts("writer")[0]["text"])
        self.bridge._objects = [near]                                                      # pehli build hata do
        self.server.queues["writer"].append(fenced(GOOD_SCRIPT)); self.server.queues["critic"].append(critique(9))
        small = self.builder().build("make a vase", out_dir=os.path.join(self.tmp.name, "v"))
        self.assertLess(((small.anchor[0] - 4.0) ** 2 + small.anchor[1] ** 2) ** 0.5, 8.0)

    def test_the_reviewer_is_told_to_check_the_type_and_solid_wheels(self):
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        self.build("make a sports car")
        system = self.posts("critic")[0]["system"]
        for phrase in ("TYPE is exactly what was asked", "NOT a pickup", "score at most 4", "wheels are SOLID"):
            self.assertIn(phrase, system)
        self.assertIn("NEVER a bare torus", self.posts("writer")[0]["system"])

    def test_reference_image_goes_to_both_writer_and_critic(self):
        ref = os.path.join(self.tmp.name, "ref.png")
        with open(ref, "wb") as handle:
            handle.write(PNG)
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        builder = self.builder()
        builder.build("make this", reference_image=ref, out_dir=os.path.join(self.tmp.name, "o"))
        self.assertEqual(self.posts("writer")[0]["images"], 1)
        self.assertEqual(self.posts("critic")[0]["images"], 5)                  # reference + 4 views
        self.assertIn("REFERENCE", self.posts("critic")[0]["system"])

    def test_iteration_limit_and_time_budget(self):
        self.writer(*[GOOD_SCRIPT] * 6)
        self.critic(*[critique(3)] * 6)
        report = self.build(max_iterations=2)
        self.assertEqual(len(report.iterations), 2)
        self.assertEqual(report.llm_calls, 4)
        ticks = iter(range(0, 100000, 400))
        timed = sc.SelfCorrectingBuilder(self.caller, self.registry, self.bridge, sc.GeminiClient(self.cfg),
                                         sc.BuilderConfig(**{**self.cfg.__dict__, "max_seconds": 500.0}), clock=lambda: next(ticks))
        self.writer(*[GOOD_SCRIPT] * 6)
        self.critic(*[critique(3)] * 6)
        out = timed.build("x", out_dir=os.path.join(self.tmp.name, "t"))
        self.assertIn("time budget", out.stopped_reason)

    def test_status_callback_reports_phases(self):
        messages = []
        self.writer(GOOD_SCRIPT)
        self.critic(critique(9))
        cfg = sc.BuilderConfig(**self.cfg.__dict__)
        builder = sc.SelfCorrectingBuilder(self.caller, self.registry, self.bridge, sc.GeminiClient(cfg), cfg, status=messages.append)
        builder.build("x", out_dir=os.path.join(self.tmp.name, "s"))
        text = " | ".join(messages)
        for phrase in ("writing the script", "building", "rendering views", "checking the renders"):
            self.assertIn(phrase, text)


class TestToolAndSkill(LoopCase):

    def setUp(self):
        super().setUp()
        # Aapke 991 downloaded models mein 'robot' bhi hai => skill (sahi taur par) library_props ko chhod deti. Test us par nirbhar na ho.
        from blender_ai_agent.tools import local_assets_tools
        self._saved_env = os.environ.get("BLENDER_AI_MODELS_DIR")
        os.environ["BLENDER_AI_MODELS_DIR"] = self.tmp.name
        local_assets_tools._INDEX_CACHE.clear()
        self.addCleanup(self._restore_models_env)

    def _restore_models_env(self):
        from blender_ai_agent.tools import local_assets_tools
        if self._saved_env is None:
            os.environ.pop("BLENDER_AI_MODELS_DIR", None)
        else:
            os.environ["BLENDER_AI_MODELS_DIR"] = self._saved_env
        local_assets_tools._INDEX_CACHE.clear()

    def tool(self, **cfg_overrides):
        cfg = sc.BuilderConfig(**{**self.cfg.__dict__, "output_dir": os.path.join(self.tmp.name, "builds"), **cfg_overrides})
        return BuildIterateTool(self.bridge, lambda: self.caller, lambda: self.registry, config_loader=lambda: cfg)

    def test_the_tool_reports_score_problems_and_files(self):
        self.writer(GOOD_SCRIPT)
        self.critic(critique(6.5, ["wheels look flat"], summary="meh"))
        result = self.tool(max_iterations=1).execute({"request": "make a thing"})
        self.assertTrue(result.success, result.error)
        data = result.data
        self.assertEqual((data["best_score"], data["reached_target"]), (6.5, False))
        self.assertIn("nahi hai", data["note"])
        self.assertEqual(data["iterations"][0]["problems"], ["wheels look flat"])
        self.assertTrue(os.path.isfile(data["script_file"]))
        self.assertEqual(len(data["view_images"]), 4)

    def test_input_validation_and_missing_setup(self):
        for bad in ({"request": ""}, {"request": "x", "max_iterations": 99}, {"request": "x", "target_score": 11}):
            self.assertFalse(self.tool().execute(bad).success, str(bad))
        self.assertEqual(BuildIterateInput(request="x", max_iterations="2", target_score="7.5", location="1, 2, 0").location, [1, 2, 0])
        no_key = BuildIterateTool(self.bridge, lambda: self.caller, lambda: self.registry, config_loader=lambda: sc.BuilderConfig(api_key=""))
        self.assertIn("GEMINI_API_KEY", no_key.execute({"request": "x"}).error)
        self.assertIn("nahi mili", self.tool().execute({"request": "x", "reference_image": "C:/nope/missing.png"}).error)

    def test_total_failure_is_a_failure_with_the_reason(self):
        self.writer(BAD_TOOL_SCRIPT)
        result = self.tool(max_iterations=1).execute({"request": "make a thing"})
        self.assertFalse(result.success)
        self.assertIn("aakhri galti", result.error)

    def test_metadata_tells_the_llm_when_and_how(self):
        description = self.tool().description
        for word in ("WRITE A BUILD SCRIPT", "RENDER", "vision", "reference_image", "score"):
            self.assertIn(word, description)

    def skill(self, key="k"):
        loader = lambda: sc.BuilderConfig(api_key=key)  # noqa: E731
        return IterativeBuildSkill(self.caller, config_loader=loader)

    def test_skill_takes_hard_requests_only_with_a_key(self):
        skill = self.skill()
        for text in ("make a realistic sports car", "create a detailed dragon", "build a robot", "a realistic horse statue",
                     "turn the image at C:\\pics\\car.png into a car"):
            self.assertEqual(skill.can_handle(text), 0.94, text)
        for text in ("make a campfire", "make a cartoon girl", "add a bottle", "make the car red", "make 3 realistic cars", "make a low poly car",
                     "do something nice", "make the dragon look broken"):
            self.assertEqual(skill.can_handle(text), 0.0, text)
        self.assertEqual(self.skill(key="").can_handle("make a realistic sports car"), 0.0)

    def test_skill_runs_the_tool_and_passes_the_reference_image(self):
        calls = []

        class Spy(Tool):
            name = "build.iterate"
            description = "spy"
            permission = Permission.SAFE_WRITE
            input_model = BuildIterateInput

            def run(self, v):
                calls.append(v)
                return ToolResult.ok({"best_score": 8.0, "objects": ["X"]})
        self.registry.register(Spy())
        skill = self.skill()
        result = skill.execute({"task": 'make a car from the image at "C:\\pics\\car.png"'})
        self.assertTrue(result.success, result.error)
        self.assertEqual(calls[0].reference_image, "C:\\pics\\car.png")
        self.assertEqual(result.data["assessment"]["route"], "from_image")
        plain = skill.execute({"task": "make a realistic sports car"})
        self.assertIsNone(calls[1].reference_image)
        self.assertEqual(plain.steps_completed, ["build.iterate:8/10"])

    def test_a_downloaded_model_wins_over_building_for_a_plain_request(self):
        skill = self.skill()
        self.assertEqual(skill.can_handle("build a robot"), 0.94)                      # abhi koi downloaded model nahi
        entry = {"id": "k-robot", "name": "Robot_Walker", "project": "pm-k", "project_name": "kenney", "collection_description": "",
                 "attributes": {}, "tags": ["robot"], "file": "kenney/Robot_Walker.glb", "size": 10, "license": "CC0"}
        with open(os.path.join(self.tmp.name, "index.json"), "w", encoding="utf-8") as handle:
            json.dump({"models": [entry]}, handle)
        from blender_ai_agent.tools import local_assets_tools
        local_assets_tools._INDEX_CACHE.clear()
        self.assertEqual(skill.can_handle("build a robot"), 0.0)                       # downloaded mila => library_props lega
        self.assertEqual(skill.can_handle("build a realistic robot"), 0.94)            # 'realistic' maanga => ab bhi build

    def test_registry_routing(self):
        registry = SkillRegistry()
        registry.register(self.skill())
        self.assertEqual(registry.find_best_match("make a realistic sports car").name, "iterative_build")
        self.assertIsNone(registry.find_best_match("make a campfire"))


if __name__ == "__main__":
    unittest.main()