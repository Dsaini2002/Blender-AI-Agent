"""Villa run (live trace 21:07): a Gemini 429 made one time.sleep() last 15+ minutes, an older run kept going in the
background next to the new one, the simple house skill took a long villa spec, and a tool came back as
'call:mesh.boundary_wall'."""

from . import _bpy_stub  # noqa: F401

import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.copilot import activity
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.providers import base
from blender_ai_agent.providers.gemini_provider import GeminiProvider, RateLimited
from blender_ai_agent.tools.object_tools import CreateObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from .fakes_ext import FakeBridge

VILLA = ("Create a realistic luxury 2-storey villa (G+1) on a flat green lawn.\n\nBuilding:\n- L-shaped villa, 2 floors\n"
         "- Main entrance with a canopy and a name board \"SAINI VILLA\"\nOutside:\n- Small swimming pool beside the house\n"
         "- Boundary wall with a gate\n- Garden with palm trees and benches")


class TestRetryWait(unittest.TestCase):

    def test_long_waits_are_refused_not_slept(self):
        started = time.monotonic()
        with self.assertRaises(RuntimeError) as caught:
            base.retry_wait(3600, "Gemini")
        self.assertLess(time.monotonic() - started, 1.0)
        self.assertIn("429", str(caught.exception))                 # still reads as a quota error

    def test_stop_ends_the_wait_at_once(self):
        activity._active.set()
        activity._stop.clear()
        try:
            threading.Timer(0.2, activity._stop.set).start()
            started = time.monotonic()
            with self.assertRaises(RuntimeError) as caught:
                base.retry_wait(15, "Gemini")
            self.assertLess(time.monotonic() - started, 2.0)
            self.assertIn("Stopped", str(caught.exception))
        finally:
            activity._stop.clear()
            activity._active.clear()

    def test_gemini_daily_quota_is_not_waited_for(self):
        provider = GeminiProvider.__new__(GeminiProvider)

        class Model:
            def generate_content(self, contents, **kwargs):
                raise RuntimeError("429 Quota exceeded for metric: generate_requests_per_model_per_day, limit: 250. "
                                   "Please retry in 41237s.")

        with mock.patch.object(base, "time") as fake_time:
            with self.assertRaises(RuntimeError) as caught:
                provider._generate_with_retry(Model(), [], max_inline_wait=None)
            fake_time.sleep.assert_not_called()
        self.assertIn("quota is used up", str(caught.exception))
        with self.assertRaises(RateLimited):                            # a fallback model is tried instead
            provider._generate_with_retry(Model(), [], max_inline_wait=15.0)

    def test_sdk_call_gets_a_timeout(self):
        provider = GeminiProvider.__new__(GeminiProvider)
        seen = {}

        class Model:
            def generate_content(self, contents, **kwargs):
                seen.update(kwargs)
                return "ok"

        self.assertEqual(provider._generate_with_retry(Model(), []), "ok")
        self.assertEqual(seen["request_options"]["timeout"], GeminiProvider.TIMEOUT_S)


class TestQuotaSwitch(unittest.TestCase):

    def test_run_waits_for_the_same_ai_when_the_quota_is_gone(self):
        class Agent:
            role_hint, tool_filter = "", None

            def __init__(self):
                self._model_provider = "gemini-provider"
                self.messages = []

            def run(self, message, state=None):
                self.messages.append(message)
                if len(self.messages) == 1:
                    raise RuntimeError("429 Gemini quota is used up (retry in 41237s).")
                return SimpleNamespace(reply_text="built with gemini", task_id="t",
                                       rolled_back=False, stopped_reason="stop")

        agent = Agent()
        controller = CopilotController(agent, auto_split=False)
        controller.current_provider_name = "gemini"
        now = [0.0]
        controller._quota_clock = lambda: now[0]
        controller._quota_sleep = lambda s: now.__setitem__(0, now[0] + s)
        result = controller._submit("make a red cube")
        self.assertTrue(result.success, result.reply_text)
        self.assertEqual(result.reply_text, "built with gemini")
        self.assertEqual(agent._model_provider, "gemini-provider")             # the same AI, never another
        self.assertIn("quota ran out", agent.messages[1])                        # it goes on, does not rebuild
        self.assertGreaterEqual(now[0], 41237)

    def test_stop_ends_the_wait(self):
        class Agent:
            role_hint, tool_filter, _model_provider = "", None, "x"

            def run(self, message, state=None):
                raise RuntimeError("429 Gemini quota is used up (retry in 41237s).")

        controller = CopilotController(Agent(), auto_split=False)
        controller.current_provider_name = "gemini"
        now = [0.0]
        controller._quota_clock = lambda: now[0]

        def sleep(seconds):
            now[0] += seconds
            if now[0] > 60:
                controller._cancelled = True                                     # the user pressed Stop
        controller._quota_sleep = sleep
        result = controller._submit("make a red cube")
        self.assertFalse(result.success)
        self.assertLess(now[0], 100)

    def test_no_other_ai_gives_the_quota_message(self):
        class Agent:
            role_hint, tool_filter, _model_provider = "", None, "x"

            def run(self, message, state=None):
                raise RuntimeError("429 Gemini quota is used up.")

        class Registry:
            def list_providers(self):
                return ["mock", "gemini"]

        controller = CopilotController(Agent(), auto_split=False)
        controller.current_provider_name = "gemini"
        with mock.patch("blender_ai_agent.get_provider_registry", return_value=Registry()):
            result = controller._submit("make a red cube")
        self.assertFalse(result.success)


class TestSpecsGoToTheTeam(unittest.TestCase):

    def test_house_skill_only_for_short_requests(self):
        from blender_ai_agent.skills.builtins.house_builder import HouseBuilderSkill
        skill = HouseBuilderSkill(None)
        self.assertGreater(skill.can_handle("make a house"), 0.0)
        self.assertEqual(skill.can_handle(VILLA), 0.0)

    def test_team_plan_ignores_skills_for_a_long_spec(self):
        class Registry:
            def find_best_match(self, task):
                return SimpleNamespace(name="house_builder")

        class Planner:
            last_source, last_raw = "lead", ""

            def plan(self, request):
                from blender_ai_agent.multi_agent.team import TeamStep
                return [TeamStep("layout", "villa"), TeamStep("modeling", "garden")]

        agent = SimpleNamespace(role_hint="", tool_filter=None, _logger=None)
        controller = CopilotController(agent, auto_split=False, skill_registry=Registry(), tool_caller=object(),
                                       team_planner=Planner())
        self.assertEqual(len(controller._team_plan(VILLA)), 2)
        self.assertEqual(controller._team_plan("make a house"), [])            # short: the skill may take it


class TestToolNames(unittest.TestCase):

    def test_prefixed_names_are_understood(self):
        bridge = FakeBridge()
        registry = ToolRegistry()
        registry.register(CreateObjectTool(bridge))
        caller = ToolCaller(registry)
        for name in ("call:object.create", "functions.object.create", "default_api.object.create", "object__create"):
            result = caller.call(ToolCall(name, {"name": f"box_{len(bridge.get_objects())}", "primitive": "CUBE"}))
            self.assertTrue(result.success, (name, result.error))
        self.assertFalse(caller.call(ToolCall("call:nothing.here", {})).success)


class TestBackgroundRun(unittest.TestCase):

    def test_a_background_run_blocks_a_new_one_and_is_told_to_stop(self):
        from blender_ai_agent.ui import panel
        gate = threading.Event()
        thread = threading.Thread(target=gate.wait, daemon=True)
        thread.start()
        controller = SimpleNamespace(cancelled=False)
        controller.cancel = lambda: setattr(controller, "cancelled", True)
        panel._WORKER.update(thread=thread, controller=controller)
        try:
            self.assertTrue(panel.worker_alive())
            panel.stop_background_run()
            self.assertTrue(controller.cancelled)
        finally:
            gate.set()
            thread.join(1)
            panel._WORKER.update(thread=None, controller=None)
        self.assertFalse(panel.worker_alive())


if __name__ == "__main__":
    unittest.main()
