from . import _bpy_stub  # noqa: F401

import unittest
from unittest.mock import MagicMock, patch

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.providers.gemini_provider import GeminiProvider, RateLimited
from .fakes import FakeBridge
from .test_repair_loop import build_repair_loop


def tool_response(*calls):
    return ModelResponse(
        content=None,
        tool_calls=[ToolCall(tool_name=n, arguments=a) for n, a in calls],
        finish_reason="tool_calls",
    )


def text_response(text="done"):
    return ModelResponse(content=text, tool_calls=[], finish_reason="stop")


class TestLoopGuards(unittest.TestCase):

    def test_duplicate_successful_call_is_skipped(self):
        create = ("object.create", {"primitive": "CUBE", "name": "car_body"})
        loop, bridge, _ = build_repair_loop([
            tool_response(create),
            tool_response(create),     # exact repeat -> skipped
            text_response(),
        ])
        result = loop.run("make a car")
        self.assertEqual(result.stopped_reason, "stop")
        self.assertEqual(len(result.executed_steps), 1)   # sirf ek baar execute hua

    def test_repeating_model_is_stopped_early_with_no_progress(self):
        create = ("object.create", {"primitive": "CUBE", "name": "car_body"})
        loop, _, _ = build_repair_loop(
            [tool_response(create)] * 10, max_iterations=25,
        )
        result = loop.run("make a car")
        self.assertEqual(result.stopped_reason, "no_progress")
        self.assertLess(result.turns_used, 6)
        self.assertNotIn("step limit", result.reply_text)

    def test_ledger_lists_completed_work(self):
        loop, _, _ = build_repair_loop([text_response()])
        record = MagicMock()
        record.tool_result.success = True
        record.tool_call.tool_name = "object.create"
        record.tool_call.arguments = {"name": "car_body"}
        ledger = loop._progress_ledger([record])
        self.assertIn("object.create(name=car_body)", ledger)
        self.assertIn("do NOT repeat", ledger)


class TestFailureTolerance(unittest.TestCase):

    def _bad_then_good(self, max_failed):
        bad = ("object.transform", {"name": "table_cloth", "location": [0, 0, 1]})
        good = ("object.create", {"primitive": "CUBE", "name": "chair_seat"})
        loop, bridge, _ = build_repair_loop([
            tool_response(bad, good),
            text_response("ok"),
        ])
        loop._max_failed_steps = max_failed
        return loop.run("add chairs")

    def test_single_stale_name_does_not_kill_task_when_tolerant(self):
        result = self._bad_then_good(max_failed=3)
        self.assertFalse(result.rolled_back)
        self.assertEqual(result.stopped_reason, "stop")
        self.assertEqual(result.executed_steps[-1].tool_call.tool_name, "object.create")

    def test_default_still_rolls_back_on_first_failure(self):
        result = self._bad_then_good(max_failed=1)
        self.assertTrue(result.rolled_back)


class TestGeminiFallback(unittest.TestCase):

    def _provider(self, models):
        p = object.__new__(GeminiProvider)
        p._genai = MagicMock()
        p._model_name = "gemini-3.1-pro-preview"
        p._fallback_models = ["gemini-3.5-flash-lite"]
        p._genai.GenerativeModel.side_effect = lambda model_name, tools=None: models[model_name]
        p._build_tools = lambda t: []
        p._build_contents = lambda m: []
        p._parse_response = lambda r: r
        return p

    class _Model:
        def __init__(self, err=None):
            self.err = err

        def generate_content(self, contents):
            if self.err:
                raise RuntimeError(self.err)
            return "OK"

    @patch("blender_ai_agent.providers.gemini_provider.time.sleep")
    def test_long_429_switches_model_without_sleeping(self, mock_sleep):
        models = {
            "gemini-3.1-pro-preview": self._Model("429 Please retry in 55.0s."),
            "gemini-3.5-flash-lite": self._Model(),
        }
        p = self._provider(models)
        req = MagicMock(tools=[], messages=[])
        self.assertEqual(p.generate(req), "OK")
        mock_sleep.assert_not_called()
        self.assertEqual(p._model_name, "gemini-3.5-flash-lite")   # sticky

    @patch("blender_ai_agent.providers.gemini_provider.time.sleep")
    def test_short_429_still_retries_same_model(self, mock_sleep):
        m = self._Model("429 Please retry in 2.0s.")
        calls = {"n": 0}
        orig = m.generate_content

        def flaky(contents):
            calls["n"] += 1
            if calls["n"] == 1:
                return orig(contents)
            return "OK"
        m.generate_content = flaky
        p = self._provider({"gemini-3.1-pro-preview": m})
        p._fallback_models = []
        self.assertEqual(p.generate(MagicMock(tools=[], messages=[])), "OK")
        mock_sleep.assert_called_once()


class TestSceneContextShowsMaterials(unittest.TestCase):

    def test_context_text_includes_material_name(self):
        from blender_ai_agent.agent.context import ContextManager
        tool = MagicMock()
        tool.execute.return_value.success = True
        tool.execute.return_value.data = {"objects": [
            {"name": "car_body", "type": "MESH", "location": [0, 0, 0.5],
             "scale": [1.5, 0.7, 0.25], "materials": ["car_red"]}]}
        text = ContextManager(tool).build_context_text()
        self.assertIn("material=car_red", text)


if __name__ == "__main__":
    unittest.main()


class TestVisionCheckEnforced(unittest.TestCase):
    """Hinglish: Agar vision.observe registered hai, render ho chuka hai, aur
    build bada hai (>4 parts), to model bina vision.observe call kiye
    'done' nahi bol sakta - loop ek baar nudge karta hai."""

    def _build_loop_with_vision(self, scripted_responses, vision_tool=None):
        from blender_ai_agent.agent.context import ContextManager
        from blender_ai_agent.agent.planner import Planner
        from blender_ai_agent.agent.repair_loop import RepairableExecutionLoop
        from blender_ai_agent.agent.tool_caller import ToolCaller
        from blender_ai_agent.inspectors.scene_inspector import SceneInspector
        from blender_ai_agent.observability.logger import Logger
        from blender_ai_agent.providers.mock_provider import MockProvider
        from blender_ai_agent.reliability.recovery import RecoveryManager
        from blender_ai_agent.tools.camera_tools import RenderPreviewTool
        from blender_ai_agent.tools.object_tools import CreateObjectTool
        from blender_ai_agent.tools.registry import ToolRegistry
        from blender_ai_agent.tools.scene_tools import SceneInspectTool

        bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(CreateObjectTool(bridge))
        registry.register(RenderPreviewTool(bridge))
        inspector = SceneInspector(bridge)
        registry.register(SceneInspectTool(inspector))
        if vision_tool is not None:
            registry.register(vision_tool)

        tool_caller = ToolCaller(registry)
        context_manager = ContextManager(registry.get("scene.inspect"))
        provider = MockProvider(responses=scripted_responses)
        loop = RepairableExecutionLoop(
            model_provider=provider,
            tool_caller=tool_caller,
            context_manager=context_manager,
            planner=Planner(),
            bridge=bridge,
            recovery_manager=RecoveryManager(tool_caller),
            logger=Logger(),
            max_iterations=10,
        )
        return loop, bridge

    def _fake_vision_tool(self, issues_sequence=None):
        from blender_ai_agent.tools.base import Permission, Tool, ToolResult

        # Hinglish: issues_sequence diya jaaye to har successive call ek
        # alag result deta hai (jaise pehli baar issues, dusri baar clean)
        # - multi-round improve loop test karne ke liye.
        call_count = {"n": 0}

        class _FakeVisionTool(Tool):
            name = "vision.observe"
            description = "fake"
            permission = Permission.READ_ONLY

            def run(self, validated_input):
                if issues_sequence is not None:
                    idx = min(call_count["n"], len(issues_sequence) - 1)
                    issues = issues_sequence[idx]
                    call_count["n"] += 1
                    return ToolResult.ok({"description": "checked", "issues": issues, "confidence": 0.9})
                return ToolResult.ok({"description": "looks fine", "issues": [], "confidence": 0.9})

        return _FakeVisionTool()

    def _create_calls(self, n):
        return [("object.create", {"primitive": "CUBE", "name": f"part_{i}"}) for i in range(n)]

    def test_finishing_without_vision_check_gets_nudged_then_succeeds(self):
        creates = self._create_calls(5)
        render = ("render.preview", {"filepath": "/tmp/x.png"})
        vision = ("vision.observe", {})
        loop, bridge = self._build_loop_with_vision(
            scripted_responses=[
                tool_response(*creates, render),
                text_response("All done, looks great!"),   # tries to finish WITHOUT vision check
                tool_response(vision),                      # nudged -> calls vision.observe
                text_response("Verified and done."),
            ],
            vision_tool=self._fake_vision_tool(),
        )
        result = loop.run("build a 5 part thing")
        self.assertEqual(result.stopped_reason, "stop")
        self.assertIn("vision.observe", [s.tool_call.tool_name for s in result.executed_steps])
        self.assertEqual(result.reply_text, "Verified and done.")

    def test_small_build_does_not_require_vision_check(self):
        creates = self._create_calls(2)   # <= 4 parts, exempt
        render = ("render.preview", {"filepath": "/tmp/x.png"})
        loop, bridge = self._build_loop_with_vision(
            scripted_responses=[tool_response(*creates, render), text_response("Done.")],
            vision_tool=self._fake_vision_tool(),
        )
        result = loop.run("build 2 cubes")
        self.assertEqual(result.stopped_reason, "stop")
        self.assertNotIn("vision.observe", [s.tool_call.tool_name for s in result.executed_steps])

    def test_no_vision_tool_registered_never_nudges(self):
        creates = self._create_calls(5)
        render = ("render.preview", {"filepath": "/tmp/x.png"})
        loop, bridge = self._build_loop_with_vision(
            scripted_responses=[tool_response(*creates, render), text_response("Done.")],
            vision_tool=None,   # vision.observe not available at all
        )
        result = loop.run("build a 5 part thing")
        self.assertEqual(result.stopped_reason, "stop")
        self.assertEqual(result.reply_text, "Done.")


class TestVisionControlledMultiRoundImprove(unittest.TestCase):
    """Hinglish: VisualQualityOptimizer-style controlled loop - render ->
    vision.observe -> agar issues hain to fix + phir se check -> jab tak
    issues khatam na ho ya MAX_VISION_ITERATIONS (3) na aa jaye."""

    def _build(self, scripted_responses, issues_sequence):
        from blender_ai_agent.agent.context import ContextManager
        from blender_ai_agent.agent.planner import Planner
        from blender_ai_agent.agent.repair_loop import RepairableExecutionLoop
        from blender_ai_agent.agent.tool_caller import ToolCaller
        from blender_ai_agent.inspectors.scene_inspector import SceneInspector
        from blender_ai_agent.observability.logger import Logger
        from blender_ai_agent.providers.mock_provider import MockProvider
        from blender_ai_agent.reliability.recovery import RecoveryManager
        from blender_ai_agent.tools.camera_tools import RenderPreviewTool
        from blender_ai_agent.tools.object_tools import CreateObjectTool
        from blender_ai_agent.tools.registry import ToolRegistry
        from blender_ai_agent.tools.scene_tools import SceneInspectTool

        bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(CreateObjectTool(bridge))
        registry.register(RenderPreviewTool(bridge))
        registry.register(SceneInspectTool(SceneInspector(bridge)))
        registry.register(self._fake_vision_tool(issues_sequence))

        tool_caller = ToolCaller(registry)
        context_manager = ContextManager(registry.get("scene.inspect"))
        provider = MockProvider(responses=scripted_responses)
        loop = RepairableExecutionLoop(
            model_provider=provider,
            tool_caller=tool_caller,
            context_manager=context_manager,
            planner=Planner(),
            bridge=bridge,
            recovery_manager=RecoveryManager(tool_caller),
            logger=Logger(),
            max_iterations=15,
        )
        return loop

    _fake_vision_tool = TestVisionCheckEnforced._fake_vision_tool

    def test_issues_reported_then_fixed_then_reconfirmed_clean(self):
        creates = [("object.create", {"primitive": "CUBE", "name": f"p{i}"}) for i in range(5)]
        render = ("render.preview", {"filepath": "/tmp/x.png"})
        vision = ("vision.observe", {})
        fix = ("object.create", {"primitive": "CUBE", "name": "fixed_wheel"})

        loop = self._build(
            scripted_responses=[
                tool_response(*creates, render),
                text_response("Done!"),                 # tries to finish -> nudged (no check yet)
                tool_response(vision),                   # 1st check -> issues reported
                text_response("Fixed it, done."),        # tries to finish -> re-nudged (issues remain)
                tool_response(fix, vision),               # fixes + 2nd check -> clean
                text_response("All good now."),
            ],
            issues_sequence=[["left wheel is floating"], []],
        )
        result = loop.run("build a car")
        self.assertEqual(result.stopped_reason, "stop")
        self.assertEqual(result.reply_text, "All good now.")
        vision_calls = [s for s in result.executed_steps if s.tool_call.tool_name == "vision.observe"]
        self.assertEqual(len(vision_calls), 2)

    def test_never_exceeds_max_vision_iterations_even_if_issues_persist(self):
        from blender_ai_agent.agent.repair_loop import RepairableExecutionLoop
        creates = [("object.create", {"primitive": "CUBE", "name": f"p{i}"}) for i in range(5)]
        render = ("render.preview", {"filepath": "/tmp/x.png"})
        vision = ("vision.observe", {})

        # Model keeps "finishing" and getting re-nudged; issues never clear.
        responses = [tool_response(*creates, render)]
        for _ in range(6):
            responses.append(text_response("Done."))
            responses.append(tool_response(vision))
        responses.append(text_response("Giving up, done."))

        loop = self._build(
            scripted_responses=responses,
            issues_sequence=[["still floating"]] * 10,  # never clears
        )
        result = loop.run("build a car")
        vision_calls = [s for s in result.executed_steps if s.tool_call.tool_name == "vision.observe"]
        self.assertLessEqual(len(vision_calls), RepairableExecutionLoop.MAX_VISION_ITERATIONS)
        self.assertEqual(result.stopped_reason, "stop")  # eventually allowed to finish, never infinite


if __name__ == "__main__":
    unittest.main()