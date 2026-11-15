from . import _bpy_stub  # noqa: F401

import json
import os
import tempfile
import unittest

from blender_ai_agent.agent.models import ModelResponse
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.memory.live import LiveMemory
from blender_ai_agent.multi_agent.team import is_big_request
from blender_ai_agent.routing.model_router import ModelTier, RoutingProvider
from .test_repair_loop import build_repair_loop

SPEC = """Create a colorful water park scene.
Main pool: rectangular, 12m x 8m, light blue water.
Next to the pool, a tall water slide tower with a spiral slide.
Always keep the water transparent and blue.
Add palm trees around the pool.
Add sun loungers with umbrellas.
A small snack bar building with a red roof.
Lighting: bright sunny day.
Camera: wide 3/4 view of the whole park.
Materials: tiles around the pool should be white."""


class Recorder:
    def __init__(self, name):
        self.name, self.calls = name, 0

    def generate(self, request):
        self.calls += 1
        return ModelResponse(content="done")


class TestLongSpec(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = os.environ.get("BLENDER_AI_LOG_DIR")
        os.environ["BLENDER_AI_LOG_DIR"] = self.tmp.name

    def tearDown(self):
        if self.old is None:
            os.environ.pop("BLENDER_AI_LOG_DIR", None)
        else:
            os.environ["BLENDER_AI_LOG_DIR"] = self.old
        self.tmp.cleanup()

    def test_a_long_spec_is_one_request_not_line_steps(self):
        loop, _, _ = build_repair_loop([ModelResponse(content="built the park")])
        controller = CopilotController(loop, auto_split=True)
        self.assertEqual(controller._plan(SPEC), [SPEC])
        self.assertEqual(controller._plan("make a campfire\nadd a tent\nadd a lantern"),
                         ["make a campfire", "add a tent", "add a lantern"])

    def test_steps_are_routed_by_the_whole_request(self):
        loop, _, _ = build_repair_loop([ModelResponse(content="a"), ModelResponse(content="b"), ModelResponse(content="c")])
        fast, strong = Recorder("fast"), Recorder("strong")
        loop._model_provider = RoutingProvider(fast, strong)
        controller = CopilotController(loop, auto_split=True)
        controller.submit("design a park\nmake it red\nrename it to Park")
        self.assertEqual(fast.calls, 0)                    # 'make it red' is trivial alone, but part of a big job
        self.assertEqual(loop._model_provider.tier, ModelTier.STRONG)

    def test_spec_lines_are_not_saved_as_preferences(self):
        memory = LiveMemory()
        loop, _, _ = build_repair_loop([ModelResponse(content="ok")])
        CopilotController(loop, auto_split=False, memory=memory).submit(SPEC)
        self.assertEqual(memory.preferences(), [])
        self.assertEqual(LiveMemory().learn_from_request("always keep the water blue"), [])
        self.assertEqual(len(LiveMemory().learn_from_request("I prefer low poly models")), 1)

    def test_unsaved_files_do_not_share_project_memory(self):
        memory = LiveMemory()
        memory.record_task("make a waterfall", "ok", ["Cliff", "Water"], "unsaved")
        self.assertNotIn("Built earlier in this file", memory.context_for("make a park", "unsaved"))

    def test_team_is_only_for_scenes_and_specs(self):
        self.assertTrue(is_big_request(SPEC))
        self.assertTrue(is_big_request("design a living room"))
        self.assertFalse(is_big_request("make a red cube"))
        self.assertFalse(is_big_request("make a car with four wheels"))

    def test_every_request_writes_a_run_log(self):
        loop, _, _ = build_repair_loop([ModelResponse(content="ok")])
        controller = CopilotController(loop, auto_split=False)
        controller.submit("make a cube")
        files = [f for f in os.listdir(self.tmp.name) if f.endswith(".json")]
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.tmp.name, files[0]), encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["request"], "make a cube")
        self.assertTrue(any(e["event"] == "task.complete" for e in data["events"]))


if __name__ == "__main__":
    unittest.main()
