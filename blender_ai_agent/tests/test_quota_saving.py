from . import _bpy_stub  # noqa: F401

import unittest
from types import SimpleNamespace

from blender_ai_agent.agent.models import ModelResponse
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.multi_agent.team import PLANNER_PROMPT, role_brief
from .test_repair_loop import build_repair_loop


class FakeVerifier:
    cfg = SimpleNamespace(mode="full", max_rounds=0)

    def begin(self, *a, **k):
        return None


class TestNoDuplicateVision(unittest.TestCase):

    def test_agent_does_not_get_vision_tool_when_the_automatic_check_reviews_renders(self):
        loop, _, _ = build_repair_loop([ModelResponse(content="ok")])
        loop._tool_caller._registry.register(SimpleNamespace(name="vision.observe", description="v", input_model=None))
        seen = []
        original = loop._build_request
        loop._build_request = lambda state, steps=None: seen.append(original(state, steps)) or seen[-1]
        CopilotController(loop, auto_split=False, verifier=FakeVerifier()).submit("make a cube")
        self.assertFalse(loop.vision_nudges)
        self.assertNotIn("vision.observe", [t.name for t in seen[0].tools])

    def test_without_the_check_the_agent_keeps_vision(self):
        loop, _, _ = build_repair_loop([ModelResponse(content="ok")])
        CopilotController(loop, auto_split=False).submit("make a cube")
        self.assertTrue(loop.vision_nudges)


class TestTeamPrompts(unittest.TestCase):

    def test_open_requests_get_a_rich_plan_and_thorough_specialists(self):
        self.assertIn("10-25 objects", PLANNER_PROMPT)
        self.assertIn("never one primitive", role_brief("modeling", "create a water park", "slides", 2, 4))


if __name__ == "__main__":
    unittest.main()
