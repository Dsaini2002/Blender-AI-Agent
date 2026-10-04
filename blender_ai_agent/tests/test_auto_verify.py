from . import _bpy_stub  # noqa: F401

import json
import os
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

from blender_ai_agent.agent import post_verify as pv
from blender_ai_agent.agent import self_correct as sc
from blender_ai_agent.agent.console_watch import Finding
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.copilot.step_progress import ProgressHistory, ProgressTracker
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.tools.registry import ToolRegistry
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeObject
from .fakes_ext import FakeBridge


def critique(score, problems=(), summary="ok", severity="high"):
    return json.dumps({"score": score, "matches_prompt": score >= 7, "summary": summary, "keep": ["colour"],
                       "problems": [{"severity": severity, "where": "wheel", "issue": p, "fix": "move it down"} for p in problems]})


class StubLLM:
    """critic ke jawab list se; har call record."""

    def __init__(self, *answers):
        self.answers, self.calls = list(answers), []

    def generate(self, system, parts, **kw):
        self.calls.append({"system": system, "images": sum(1 for p in parts if "inline_data" in p), "text": " ".join(p.get("text", "") for p in parts)})
        if not self.answers:
            raise AssertionError("critic called more often than scripted")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class WorldAgent:
    """Asli agent ki jagah: script ke hisaab se objects banata hai aur console mein likhta hai."""

    def __init__(self, bridge, script):
        self.bridge, self.script, self.received = bridge, list(script), []
        self.controller = None

    def run(self, user_input, state=None):
        self.received.append(user_input)
        step = self.script.pop(0) if self.script else {}
        if isinstance(step.get("raise"), Exception):
            raise step["raise"]
        for name in step.get("create", []):
            self.bridge._objects.append(FakeObject(name=name, type_="MESH"))
        for name in step.get("delete", []):
            self.bridge._objects = [o for o in self.bridge._objects if o.name != name]
        for name in step.get("move", []):
            self.bridge.get_object(name).location = [9.0, 9.0, 9.0]
        if step.get("console"):
            sys.stderr.write(step["console"] + "\n")
        if step.get("cancel"):
            self.controller.cancel()
        if step.get("fail"):
            return SimpleNamespace(reply_text="could not build that", task_id="t", rolled_back=True)
        return SimpleNamespace(reply_text=step.get("reply", f"built {len(self.received)}"), task_id=f"t{len(self.received)}", rolled_back=False)


class Case(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(SceneInspectTool(SceneInspector(self.bridge)))
        self.caller = ToolCaller(registry)
        self.cfg = pv.VerifyConfig(mode="full", max_rounds=2, pass_score=7.0, fd_capture=False, output_dir=os.path.join(self.tmp.name, "checks"),
                                   min_objects_for_vision=3)
        self.llm = StubLLM()
        self.key = "k"
        sc.REVIEW_LOG.clear()

    def tearDown(self):
        self.tmp.cleanup()
        sc.REVIEW_LOG.clear()

    def verifier(self, llm=None, **overrides):
        for k, v in overrides.items():
            setattr(self.cfg, k, v)
        stub = llm or self.llm
        return pv.PostRunVerifier(self.caller, self.bridge, llm_factory=lambda cfg: stub, config_loader=lambda: self.cfg,
                                  builder_config_loader=lambda: sc.BuilderConfig(api_key=self.key))

    def controller(self, script, verifier=None, skill_registry=None, **kw):
        agent = WorldAgent(self.bridge, script)
        history = ProgressHistory(path=os.path.join(self.tmp.name, "h.json"))
        tracker = ProgressTracker(history=history, clock=time.time)
        controller = CopilotController(agent, tracker=tracker, verifier=verifier, skill_registry=skill_registry,
                                       tool_caller=self.caller if skill_registry else None, **kw)
        agent.controller = controller
        return controller, agent

    def stderr_quiet(self):
        """Test ke console-likhne wale agent ka shor user ke terminal par na aaye (par capture ko dikhe)."""
        class Quiet:
            def __init__(self, inner): self.inner = inner
            def write(self, text): return len(text)
            def flush(self): pass
            def __getattr__(self, name): return getattr(self.inner, name)
        self._real = sys.stderr
        sys.stderr = Quiet(self._real)
        self.addCleanup(lambda: setattr(sys, "stderr", self._real))


THREE = ["Car_body", "Car_wheel", "Car_lamp"]


class TestConfig(unittest.TestCase):

    def test_defaults_file_and_env(self):
        saved = os.environ.pop("BLENDER_AI_AUTOVERIFY", None)
        try:
            self.assertEqual(pv.load_verify_config("/nonexistent.json").mode, "full")
            with tempfile.TemporaryDirectory() as tmp:
                path = os.path.join(tmp, "a.json")
                with open(path, "w") as handle:
                    json.dump({"mode": "console", "max_rounds": 99, "pass_score": "6.5", "views": ["front", "top"], "junk": 1}, handle)
                cfg = pv.load_verify_config(path)
                self.assertEqual((cfg.mode, cfg.max_rounds, cfg.pass_score, cfg.views), ("console", 4, 6.5, ("front", "top")))
                os.environ["BLENDER_AI_AUTOVERIFY"] = "off"
                self.assertEqual(pv.load_verify_config(path).mode, "off")
                os.environ["BLENDER_AI_AUTOVERIFY"] = "nonsense"
                self.assertEqual(pv.load_verify_config(path).mode, "console")
                with open(path, "w") as handle:
                    handle.write("{broken")
                self.assertEqual(pv.load_verify_config(path).mode, "full")
        finally:
            os.environ.pop("BLENDER_AI_AUTOVERIFY", None)
            if saved is not None:
                os.environ["BLENDER_AI_AUTOVERIFY"] = saved


class TestSessionAndAssess(Case):

    def test_session_sees_what_was_created_changed_and_printed(self):
        self.bridge._objects.append(FakeObject(name="Old", type_="MESH"))
        self.bridge._objects.append(FakeObject(name="Moved", type_="MESH"))
        verifier = self.verifier()
        session = verifier.begin("make stuff")
        self.bridge._objects.append(FakeObject(name="New", type_="MESH"))
        self.bridge.get_object("Moved").location = [5.0, 0.0, 0.0]
        print("RuntimeError: something broke")
        facts = session.end()
        self.assertEqual((facts.created, facts.changed), (["New"], ["Moved"]))
        self.assertEqual(facts.types["New"], "MESH")
        self.assertIn("RuntimeError: something broke", facts.console_text)
        self.assertIs(session.end(), facts)                                           # dobara bulane par wahi

    def test_console_only_mode_never_renders(self):
        verifier = self.verifier(mode="console")
        facts = pv.RunFacts(created=THREE, types={n: "MESH" for n in THREE}, console_text="Warning: QuadriFlow: The mesh needs to be manifold\n",
                            started=time.time())
        report = verifier.assess("make a car", facts)
        self.assertTrue(report.needs_fix)
        self.assertEqual(len(report.actionable), 1)
        self.assertEqual(getattr(self.bridge, "render_requests", []), [])
        self.assertIsNone(report.score)

    def test_dirty_console_alone_triggers_fix_but_info_does_not(self):
        verifier = self.verifier(mode="console")
        quiet = verifier.assess("x", pv.RunFacts(console_text="\\Text:38: DeprecationWarning: 'World.use_nodes' is expected to be removed\n"))
        self.assertFalse(quiet.needs_fix)
        self.assertEqual([f.level for f in quiet.findings], ["info"])

    def test_vision_pass_and_fail_decisions(self):
        facts = pv.RunFacts(created=THREE, types={n: "MESH" for n in THREE}, started=time.time())
        good = self.verifier(llm=StubLLM(critique(8.5, summary="a car"))).assess("make a car", facts)
        self.assertEqual((good.score, good.needs_fix), (8.5, False))
        self.assertEqual(len(good.images), 3)                                          # front, right, three_quarter
        self.assertEqual(self.bridge.render_requests[-1]["names"], THREE)
        bad = self.verifier(llm=StubLLM(critique(4, ["wheel floats"]))).assess("make a car", facts)
        self.assertTrue(bad.needs_fix)
        self.assertEqual(bad.problems[0]["issue"], "wheel floats")
        minor = self.verifier(llm=StubLLM(critique(5, ["tiny nit"], severity="low"))).assess("make a car", facts)
        self.assertFalse(minor.needs_fix)                                              # sirf low severity => theek kar nahi

    def test_who_gets_a_vision_check(self):
        started = time.time()
        many = pv.RunFacts(created=THREE, types={n: "MESH" for n in THREE}, started=started)
        verifier = self.verifier(llm=StubLLM(*[critique(9)] * 10))
        self.assertIsNone(verifier.assess("make a car", many).vision_note or None)
        simple = pv.RunFacts(created=["Cube"], types={"Cube": "MESH"}, started=started)
        self.assertIn("simple request", verifier.assess("make a red cube", simple).vision_note)
        self.assertEqual(verifier.assess("make a realistic car", simple).vision_note, "")                  # mushkil subject => vision
        self.assertEqual(self.verifier(always_vision=True, llm=StubLLM(critique(9))).assess("make a red cube", simple).vision_note, "")
        self.assertIn("nothing new", verifier.assess("x", pv.RunFacts(started=started)).vision_note)
        lights = pv.RunFacts(created=["Sun", "Cam", "Lamp"], types={"Sun": "LIGHT", "Cam": "CAMERA", "Lamp": "LIGHT"}, started=started)
        self.assertIn("nothing new", verifier.assess("add lights", lights).vision_note)
        sc.REVIEW_LOG.append(time.time() + 1)
        self.assertIn("build.iterate", verifier.assess("make a car", many).vision_note)
        sc.REVIEW_LOG.clear()
        self.key = ""
        self.assertIn("GEMINI_API_KEY", verifier.assess("make a car", many).vision_note)

    def test_vision_failures_never_break_the_check(self):
        facts = pv.RunFacts(created=THREE, types={n: "MESH" for n in THREE}, started=time.time())
        for answer, fragment in ((sc.BuilderError("quota", "Gemini ka quota khatam ho gaya (429)."), "429"),
                                 ("I think it looks nice!", "could not be read"), (RuntimeError("boom"), "RuntimeError")):
            report = self.verifier(llm=StubLLM(answer)).assess("make a car", facts)
            self.assertFalse(report.needs_fix)
            self.assertIn(fragment, report.vision_note)
        self.bridge.render_fails = True
        report = self.verifier(llm=StubLLM(critique(9))).assess("make a car", facts)
        self.assertIn("render failed", report.vision_note)
        self.assertFalse(report.needs_fix)

    def test_fix_prompt_carries_everything_the_agent_needs(self):
        report = pv.CheckReport(findings=[Finding("error", "RuntimeError: boom", "redo it", True), Finding("info", "Deprecation", "", False)],
                                created=THREE, changed=["Ground"], score=4.0, summary="wheels float",
                                problems=[{"severity": "high", "where": "wheel", "issue": "floats 20cm", "fix": "lower it"}], keep=["colour"], needs_fix=True)
        text = self.verifier().fix_prompt("make a car", report, 1)
        for needed in ("AUTOMATIC CHECK (round 1)", "make a car", "Car_body, Car_wheel, Car_lamp, Ground", "RuntimeError: boom -> redo it",
                       "score 4/10", "floats 20cm -> lower it", "colour", "never objects that existed"):
            self.assertIn(needed, text)
        self.assertNotIn("Deprecation", text)

    def test_history_texts(self):
        verifier = self.verifier()
        ok = pv.CheckReport(score=8.0)
        self.assertEqual(verifier.format_history([ok]), "Auto-check ✓ (console clean, vision 8/10)")
        bad = pv.CheckReport(score=4.0, needs_fix=True, problems=[{"severity": "high", "where": "w", "issue": "floats", "fix": ""}])
        fixed = verifier.format_history([bad, ok])
        self.assertIn("fixed after 1 round(s)", fixed)
        self.assertIn("vision 4/10", fixed)
        self.assertIn("vision 8/10", fixed)
        still = verifier.format_history([bad, bad])
        self.assertIn("problems remain", still)
        self.assertIn("floats", still)
        self.assertEqual(verifier.format_history([]), "")


class TestControllerFlow(Case):

    def test_clean_build_gets_a_green_check_and_no_extra_agent_run(self):
        self.llm.answers = [critique(8.5)]
        controller, agent = self.controller([{"create": THREE}], self.verifier())
        result = controller.submit("make a car")
        self.assertTrue(result.success)
        self.assertEqual(len(agent.received), 1)
        self.assertIn("Auto-check ✓ (console clean, vision 8.5/10)", result.reply_text)
        self.assertIn("built 1", result.reply_text)
        messages = [m.content for m in controller.session.get_messages()]
        self.assertTrue(any("Auto-check ✓" in str(m) for m in messages))

    def test_console_error_makes_the_agent_fix_it_and_then_it_passes(self):
        self.stderr_quiet()
        self.llm.answers = [critique(8.0)]
        controller, agent = self.controller([{"create": THREE, "console": "Warning: QuadriFlow: The mesh needs to be manifold"},
                                             {"reply": "recalculated normals"}], self.verifier())
        result = controller.submit("make a car")
        self.assertEqual(len(agent.received), 2)
        self.assertTrue(agent.received[1].startswith("AUTOMATIC CHECK (round 1)"))
        self.assertIn("needs to be manifold", agent.received[1])
        self.assertIn("fixed after 1 round(s)", result.reply_text)
        self.assertTrue(result.success)

    def test_low_vision_score_triggers_a_fix_with_the_reviewers_notes(self):
        self.llm.answers = [critique(4, ["wheel floats 20cm"]), critique(8.2)]
        controller, agent = self.controller([{"create": THREE}, {"move": ["Car_wheel"]}], self.verifier())
        result = controller.submit("make a car")
        self.assertEqual(len(agent.received), 2)
        self.assertIn("wheel floats 20cm", agent.received[1])
        self.assertIn("score 4/10", agent.received[1])
        self.assertIn("fixed after 1 round(s)", result.reply_text)
        self.assertEqual(len(self.llm.calls), 2)
        self.assertEqual(self.llm.calls[1]["images"], 3)

    def test_rounds_are_limited_and_the_remaining_problems_are_shown(self):
        self.llm.answers = [critique(3, ["still wrong"])] * 3
        controller, agent = self.controller([{"create": THREE}, {}, {}, {}], self.verifier(max_rounds=2))
        result = controller.submit("make a car")
        self.assertEqual(len(agent.received), 3)                                       # 1 + 2 fix rounds
        self.assertIn("2 fix round(s) done, problems remain", result.reply_text)
        self.assertIn("still wrong", result.reply_text)
        self.assertTrue(result.success)                                                  # kaam to ho gaya tha

    def test_a_fix_that_makes_it_worse_stops_the_loop(self):
        self.llm.answers = [critique(6, ["meh"]), critique(3, ["much worse"])]
        controller, agent = self.controller([{"create": THREE}, {}, {}], self.verifier(max_rounds=3))
        result = controller.submit("make a car")
        self.assertEqual(len(agent.received), 2)
        self.assertIn("problems remain", result.reply_text)

    def test_fix_prompts_never_go_to_skills(self):
        executed = []

        class GreedySkill:
            name = "greedy"

            def execute(self, ctx):
                executed.append(ctx["task"])
                return SimpleNamespace(success=True, error=None, data={"k": 1}, steps_completed=["a"])

        class Registry:
            def __init__(self): self.skill = GreedySkill()
            def find_best_match(self, text): return self.skill
        self.llm.answers = [critique(4, ["bad"]), critique(9)]
        controller, agent = self.controller([{"create": THREE}], self.verifier(), skill_registry=Registry())
        # skill "banata" nahi (fake) => scene mein kuch naya nahi => pehle hi check "nothing new"; isliye objects khud bana do
        self.bridge._objects.extend(FakeObject(name=n, type_="MESH") for n in THREE)
        controller2, agent2 = self.controller([{}, {}], self.verifier(always_vision=True), skill_registry=Registry())
        self.llm.answers = [critique(4, ["bad"]), critique(9)]
        original = controller2._skill_registry.skill.execute

        def building_execute(ctx):
            for n in ("S_a", "S_b", "S_c"):
                self.bridge._objects.append(FakeObject(name=n, type_="MESH"))
            return original(ctx)
        controller2._skill_registry.skill.execute = building_execute
        controller2.submit("make a thing")
        self.assertEqual(executed, ["make a thing"])                                   # skill sirf ek baar (asli request)
        self.assertEqual(len(agent2.received), 1)
        self.assertTrue(agent2.received[0].startswith("AUTOMATIC CHECK"))              # fix agent ne kiya

    def test_off_mode_and_no_verifier_behave_exactly_as_before(self):
        for verifier in (None, self.verifier(mode="off")):
            controller, agent = self.controller([{"create": THREE, "console": "RuntimeError: x"}], verifier)
            result = controller.submit("make a car")
            self.assertEqual(result.reply_text, "built 1")
            self.assertEqual(len(agent.received), 1)

    def test_failed_or_cancelled_runs_are_not_checked(self):
        controller, agent = self.controller([{"create": THREE, "fail": True}], self.verifier())
        result = controller.submit("make a car")
        self.assertFalse(result.success)
        self.assertEqual(result.reply_text, "could not build that")
        self.assertEqual(self.llm.calls, [])
        controller, agent = self.controller([{"create": THREE, "cancel": True}], self.verifier())
        controller.submit("make a car")
        self.assertEqual(len(agent.received), 1)

    def test_quota_during_the_fix_keeps_the_original_result(self):
        quota = RuntimeError("429 You exceeded your current quota, limit: 20, model: gemini-3.6-flash")
        self.llm.answers = [critique(4, ["wheel floats"])]
        controller, agent = self.controller([{"create": THREE}, {"raise": quota}], self.verifier())
        result = controller.submit("make a car")
        self.assertTrue(result.success)
        self.assertEqual(len(agent.received), 2)
        self.assertIn("problems remain", result.reply_text)
        self.assertIn("auto-fix nahi ho paya", result.reply_text)
        self.assertNotIn("fixed after", result.reply_text)                              # jhooth nahi: fix chala hi nahi
        self.assertEqual(len(self.llm.calls), 1)                                         # fix fail => dobara vision nahi

    def test_unexpected_crash_in_the_fix_does_not_break_the_task_result(self):
        self.llm.answers = [critique(4, ["wheel floats"])]
        controller, agent = self.controller([{"create": THREE}, {"raise": ValueError("weird")}], self.verifier())
        result = controller.submit("make a car")
        self.assertTrue(result.success)
        self.assertIn("auto-fix ruk gaya", result.reply_text)
        self.assertIn("ValueError", result.reply_text)

    def test_a_broken_verifier_never_breaks_the_task(self):
        verifier = self.verifier()
        verifier.assess = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("verifier exploded"))
        controller, agent = self.controller([{"create": THREE}], verifier)
        result = controller.submit("make a car")
        self.assertTrue(result.success)
        self.assertIn("Auto-check chal nahi paya", result.reply_text)
        self.assertIn("built 1", result.reply_text)
        broken_begin = self.verifier()
        broken_begin.begin = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no snapshot"))
        controller, agent = self.controller([{"create": THREE}], broken_begin)
        self.assertEqual(controller.submit("make a car").reply_text, "built 1")

    def test_a_crashing_task_restores_the_console_and_propagates(self):
        before = sys.stderr
        controller, agent = self.controller([{"raise": ValueError("agent exploded")}], self.verifier())
        with self.assertRaises(ValueError):
            controller.submit("make a car")
        self.assertIs(sys.stderr, before)

    def test_multi_step_requests_get_one_check_at_the_end(self):
        self.llm.answers = [critique(8.4)]
        script = [{"create": ["A1", "A2"]}, {"create": ["B1"]}, {"create": ["C1"]}]
        controller, agent = self.controller(script, self.verifier())
        result = controller.submit("make a campfire, add a tent, add a lantern")
        self.assertEqual(len(agent.received), 3)
        self.assertEqual(len(self.llm.calls), 1)                                         # steps par nahi, poore par ek
        self.assertEqual(self.bridge.render_requests[-1]["names"], ["A1", "A2", "B1", "C1"])
        self.assertIn("Done 3/3 steps", result.reply_text)
        self.assertIn("Auto-check ✓", result.reply_text)

    def test_multi_step_fix_round_covers_the_whole_result(self):
        self.stderr_quiet()
        script = [{"create": ["A1", "A2"], "console": "RuntimeError: step one hurt"}, {"create": ["B1"]}, {"create": ["C1"]}, {"reply": "fixed it"}]
        self.llm.answers = [critique(9)]
        controller, agent = self.controller(script, self.verifier(mode="full"))
        result = controller.submit("make a campfire, add a tent, add a lantern")
        self.assertEqual(len(agent.received), 4)
        self.assertTrue(agent.received[3].startswith("AUTOMATIC CHECK"))
        self.assertIn("step one hurt", agent.received[3])
        self.assertIn("fixed after 1 round(s)", result.reply_text)

    def test_quota_stop_in_multi_step_skips_the_check(self):
        quota = RuntimeError("429 You exceeded your current quota, limit: 20, model: gemini-3.6-flash")
        controller, agent = self.controller([{"create": ["A1"]}, {"raise": quota}, {}], self.verifier())
        result = controller.submit("make a campfire, add a tent, add a lantern")
        self.assertEqual(self.llm.calls, [])
        self.assertNotIn("Auto-check", result.reply_text)

    def test_build_iterate_reviews_are_not_repeated(self):
        class Iterating(WorldAgent):
            def run(self, user_input, state=None):
                reply = super().run(user_input, state)
                sc.REVIEW_LOG.append(time.time())
                return reply
        agent = Iterating(self.bridge, [{"create": THREE}])
        controller = CopilotController(agent, tracker=ProgressTracker(history=ProgressHistory(path=os.path.join(self.tmp.name, "h2.json")), clock=time.time),
                                       verifier=self.verifier())
        result = controller.submit("make a realistic car")
        self.assertEqual(self.llm.calls, [])
        self.assertIn("already reviewed by build.iterate", result.reply_text)


if __name__ == "__main__":
    unittest.main()