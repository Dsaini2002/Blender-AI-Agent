from . import _bpy_stub  # noqa: F401

import json
import unittest

from blender_ai_agent.agent.models import ModelResponse, ToolCall
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.multi_agent.team import TeamPlanner, parse_plan, role_filter
from .test_repair_loop import build_repair_loop


class PlannerProvider:
    def __init__(self, steps):
        self.steps, self.requests = steps, []

    def generate(self, request):
        self.requests.append(request)
        return ModelResponse(content="Here is the plan:\n" + json.dumps({"steps": self.steps}))


class TestPlanParsing(unittest.TestCase):

    def test_parses_json_inside_text_and_drops_unknown_roles(self):
        steps = parse_plan('ok {"steps": [{"role": "layout", "task": "make a 5x4 m floor"}, '
                           '{"role": "dancer", "task": "dance a lot"}, {"role": "Lighting", "task": "add a warm lamp light"}]}')
        self.assertEqual([(s.role, s.task) for s in steps], [("layout", "make a 5x4 m floor"), ("lighting", "add a warm lamp light")])

    def test_garbage_gives_no_plan(self):
        self.assertEqual(parse_plan("sorry I cannot"), [])
        planner = TeamPlanner(lambda: PlannerProvider([{"role": "modeling", "task": "only one step here"}]))
        steps = planner.plan("design a room")              # an unusable plan falls back to the standard 4 roles
        self.assertEqual([s.role for s in steps], ["layout", "modeling", "materials", "lighting"])
        self.assertEqual(planner.last_source, "fallback")

    def test_role_tool_filters(self):
        materials = role_filter("materials")
        self.assertTrue(materials("material.recipe"))
        self.assertFalse(materials("object.create"))
        self.assertTrue(role_filter("lighting")("light.create"))
        self.assertFalse(role_filter("lighting")("mesh.sdf"))


class TestControllerTeamFlow(unittest.TestCase):

    def test_big_request_runs_as_role_steps_with_role_briefs_and_filtered_tools(self):
        loop, bridge, _ = build_repair_loop([
            ModelResponse(tool_calls=[ToolCall("object.create", {"name": "room_floor", "primitive": "PLANE"})]),
            ModelResponse(content="floor done"),
            ModelResponse(tool_calls=[ToolCall("object.create", {"name": "room_sofa", "primitive": "CUBE"})]),
            ModelResponse(content="sofa done"),
        ], max_iterations=10)
        seen = []
        original = loop._build_request

        def spy(state, steps=None):
            request = original(state, steps)
            seen.append((loop.role_hint, sorted(t.name for t in request.tools)))
            return request

        loop._build_request = spy
        planner = TeamPlanner(lambda: PlannerProvider([
            {"role": "layout", "task": "make a 5x4 m floor named room_floor"},
            {"role": "modeling", "task": "make a sofa named room_sofa on the floor"},
        ]))
        controller = CopilotController(loop, auto_split=False, team_planner=planner)
        result = controller.submit("design a small living room with a sofa")
        self.assertTrue(result.success, result.reply_text)
        self.assertIn("✓ 1. make a 5x4 m floor", result.reply_text)
        self.assertIsNotNone(bridge.get_object("room_sofa"))
        self.assertIn("LAYOUT specialist", seen[0][0])
        self.assertIn("MODELING specialist", seen[-1][0])
        self.assertEqual(loop.role_hint, "")                  # reset after the team run
        self.assertIsNone(loop.tool_filter)

    def test_small_request_skips_the_team(self):
        loop, _, _ = build_repair_loop([ModelResponse(content="ok")])
        provider = PlannerProvider([])
        controller = CopilotController(loop, auto_split=False, team_planner=TeamPlanner(lambda: provider))
        controller.submit("make a red cube")
        self.assertEqual(provider.requests, [])

    def test_team_can_be_switched_off(self):
        loop, _, _ = build_repair_loop([ModelResponse(content="ok")])
        provider = PlannerProvider([])
        controller = CopilotController(loop, auto_split=False, team_planner=TeamPlanner(lambda: provider))
        controller.team_enabled = False
        controller.submit("design a small living room with a sofa")
        self.assertEqual(provider.requests, [])


if __name__ == "__main__":
    unittest.main()
