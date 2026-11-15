from . import _bpy_stub  # noqa: F401

import os
import tempfile
import unittest

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.memory.live import LiveMemory
from blender_ai_agent.memory.store import JsonFileStore
from .test_repair_loop import build_repair_loop


class TestLiveMemory(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "memory.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_preferences_are_learned_and_survive_a_restart(self):
        memory = LiveMemory.from_file(self.path)
        saved = memory.learn_from_request("Make a chair. I prefer low poly models with wooden materials.")
        self.assertEqual(saved, ["I prefer low poly models with wooden materials"])
        memory.learn_from_request("mujhe hamesha blue color pasand hai")
        again = LiveMemory.from_file(self.path)                       # new Blender session
        self.assertEqual(len(again.preferences()), 2)
        self.assertIn("low poly", again.context_for("make a table"))

    def test_plain_requests_and_secrets_are_not_saved(self):
        memory = LiveMemory.from_file(self.path)
        self.assertEqual(memory.learn_from_request("make a red cube"), [])
        self.assertEqual(memory.learn_from_request("always use my api_key abc123 for this"), [])
        self.assertEqual(memory.context_for("make a cube"), "")

    def test_project_memory_is_per_file_and_tasks_are_recalled(self):
        memory = LiveMemory.from_file(self.path)
        memory.record_task("make a wooden table", "done", ["table_top", "table_leg_1"], "room.blend")
        self.assertIn("table_top", memory.context_for("make the table red", "room.blend"))
        self.assertNotIn("Built earlier in this file", memory.context_for("make a chair", "other.blend"))
        self.assertIn("Similar earlier requests", memory.context_for("another wooden table", "other.blend"))

    def test_forget_all_clears_the_file(self):
        memory = LiveMemory.from_file(self.path)
        memory.learn_from_request("I always want metres as units please")
        memory.forget_all()
        self.assertEqual(LiveMemory.from_file(self.path).count(), 0)

    def test_store_keeps_preferences_when_trimming(self):
        store = JsonFileStore(self.path, max_items=3)
        memory = LiveMemory(store)
        memory.learn_from_request("I prefer dark materials everywhere")
        for i in range(5):
            memory.record_task(f"make thing {i}", "ok", [], "")
        self.assertEqual(store.all().__len__(), 3)
        self.assertEqual(len(memory.preferences()), 1)


class TestControllerUsesMemory(unittest.TestCase):

    def test_memory_reaches_the_agent_and_the_task_is_recorded(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        memory = LiveMemory.from_file(os.path.join(tmp.name, "m.json"))
        memory.learn_from_request("I prefer red materials for everything")
        loop, bridge, _ = build_repair_loop([
            ModelResponse(tool_calls=[ToolCall("object.create", {"name": "Chair", "primitive": "CUBE"})]),
            ModelResponse(content="made a chair"),
        ])
        seen = []
        original = loop._build_request
        loop._build_request = lambda state, steps=None: seen.append(loop.memory_context) or original(state, steps)
        controller = CopilotController(loop, auto_split=False, memory=memory, project_id_getter=lambda: "a.blend")
        result = controller.submit("make a chair")
        self.assertTrue(result.success, result.reply_text)
        self.assertIn("red materials", seen[0])
        self.assertIn("Chair", memory.context_for("make the chair blue", "a.blend"))


if __name__ == "__main__":
    unittest.main()
