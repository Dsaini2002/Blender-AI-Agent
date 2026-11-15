"""IIT hostel campus run (log 20261114_180644): one agent built three grey 8-vertex boxes, material.recipe failed
for a missing name, the fix rounds called no tool at all, interiors were never seen by the reviewer, a hoop
stood in the middle of the court, and team mode never ran because an unusual plan was thrown away.
Also: the Claude provider."""

from . import _bpy_stub  # noqa: F401

import io
import json
import os
import unittest
import urllib.error
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent.agent import self_correct as sc
from blender_ai_agent.agent.models import Message, ModelRequest, ModelResponse, ToolCall, ToolDefinition
from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.multi_agent.team import TeamPlanner, TeamStep, fallback_plan, parse_plan
from blender_ai_agent.providers.claude_provider import (ClaudeProvider, ClaudeVisionClient, claude_messages,
                                                        from_claude_name, to_claude_name)
from blender_ai_agent.tools import field_markings as fm
from blender_ai_agent.tools.building import MeshBuildingTool
from blender_ai_agent.tools.field_markings import FieldMarkingsTool
from blender_ai_agent.tools.library_tools import LibraryPlaceTool
from blender_ai_agent.tools.render_views import building_cutaways, cutaway_pose
from blender_ai_agent.tools.shader_tools import MaterialRecipeInput
from blender_ai_agent.tools.site_tools import MeshBoundaryWallTool, SceneOrganizeTool, SceneSaveTool, TextCreateTool
from .fakes_ext import FakeBridge as _ExtBridge
from .test_repair_loop import build_repair_loop

REQUEST = ("Create a highly detailed, realistic 3D architectural model of a modern IIT student hostel campus.\n"
           "1. Main Hostel Building\n- G+5 U-shaped building with courtyard\n- 150-200 rooms\n"
           "2. Student Facilities\n- reception, mess, library, recreation with table tennis\n"
           "3. Outdoor Campus\n- basketball and badminton courts\n- bicycle parking\n- security gate and boundary walls\n"
           "7. Technical Requirements\n- Organize objects into collections: Hostel_Building, Rooms, Furniture\n"
           "- Save the completed scene as IIT_Hostel_Campus.blend.")


class Bridge(_ExtBridge):
    """The fake bridge plus text, collections and saving."""

    def __init__(self):
        super().__init__()
        self.collections, self.saved = {}, []

    def create_text(self, name, body, location=None, rotation=None, size=1.0, extrude=0.0, align="CENTER"):
        obj = self.create_object(name, object_type="FONT", location=list(location or [0, 0, 0]))
        obj.rotation_euler = list(rotation or [0, 0, 0])
        obj.text_body, obj.text_size = body, size
        return obj

    def move_to_collection(self, names, collection, parent=""):
        moved = []
        for name in names:
            obj = self.get_object(name)
            if obj is None:
                continue
            for members in self.collections.values():
                if name in members:
                    members.remove(name)
            self.collections.setdefault(collection, []).append(name)
            obj.users_collection = [SimpleNamespace(name=collection)]
            moved.append(name)
        self.collections.setdefault(collection, [])
        return {"collection": collection, "moved": moved, "missing": []}

    def save_blend(self, filepath):
        self.saved.append(filepath)
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "wb") as handle:              # a real (fake) .blend on disk: scene.save checks it
            handle.write(b"BLENDER-v500" + b"\0" * 4096)
        return {"filepath": filepath}

    def current_blend_path(self):
        return ""


def mesh_names(bridge):
    return {o.name for o in bridge.get_objects()}


class TestBuilding(unittest.TestCase):

    def test_u_shaped_hostel_has_rooms_halls_and_sign(self):
        bridge = Bridge()
        result = MeshBuildingTool(bridge).execute({"name": "hostel", "shape": "U", "floors": 6, "floor_height": 3.2,
                                                   "rooms": 180, "sign_text": "IIT STUDENT HOSTEL"})
        self.assertTrue(result.success, result.error)
        data = result.data
        self.assertEqual(data["storeys"], "G+5")
        self.assertGreaterEqual(data["rooms"], 150)
        self.assertLessEqual(data["rooms"], 200)
        for part in ("hostel_walls", "hostel_glass", "hostel_rooms", "hostel_furniture_wood", "hostel_stairs"):
            self.assertIn(part, data["objects"])
        kinds = {h["kind"] for h in data["halls"]}
        self.assertTrue({"reception", "mess"} <= kinds or {"reception", "dining"} <= kinds, kinds)
        sign = bridge.get_object("hostel_sign")
        self.assertEqual(sign.text_body, "IIT STUDENT HOSTEL")
        self.assertGreaterEqual(sign.text_size, 0.5)              # a real name board, readable from the gate
        self.assertIn("courtyard", data)
        self.assertEqual(len(data["stair_cores"]), len(data["lift_shafts"]))
        self.assertIn("Rooms", bridge.collections)

    def test_one_storey_block_has_no_stair_core(self):
        bridge = Bridge()
        result = MeshBuildingTool(bridge).execute({"name": "shop", "floors": 1, "width": 10, "depth": 8})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["stair_cores"], [])
        self.assertNotIn("shop_stairs", result.data["objects"])

    def test_bad_input_is_explained(self):
        bridge = Bridge()
        self.assertIn("rect, L, U or courtyard", MeshBuildingTool(bridge).execute({"shape": "star"}).error)
        self.assertIn("G+5 = 6", MeshBuildingTool(bridge).execute({"floors": 0}).error)


class TestSite(unittest.TestCase):

    def test_boundary_wall_gate_arch_carries_the_sign(self):
        bridge = Bridge()
        result = MeshBoundaryWallTool(bridge).execute({"name": "campus_wall", "size": [120, 120],
                                                       "sign_text": "IIT STUDENT HOSTEL"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["gate"], [0.0, -60.0])
        sign = bridge.get_object("campus_wall_gate_sign")
        self.assertIsNotNone(sign)
        self.assertLess(sign.location[1], -60.0)                 # on the outer face of the arch
        self.assertGreater(sign.location[2], 3.5)                # up on the arch, above the gate
        self.assertIn("campus_wall_gate_sign", result.data["objects"])

    def test_organize_sorts_specific_kinds_first_and_keeps_building_sorting(self):
        bridge = Bridge()
        MeshBuildingTool(bridge).execute({"name": "hostel", "shape": "U", "floors": 3})
        bridge.create_object("CampusCamera", object_type="CAMERA")
        bridge.create_object("bb_court_surface")
        bridge.create_object("campus_wall_wall")
        result = SceneOrganizeTool(bridge).execute({"collections": ["Hostel_Building", "Rooms", "Furniture", "Sports",
                                                                    "Landscaping", "Cameras"]})
        self.assertTrue(result.success, result.error)
        cols = bridge.collections
        self.assertIn("hostel_furniture_wood", cols["Furniture"])
        self.assertIn("hostel_rooms", cols["Rooms"])
        self.assertIn("hostel_walls", cols["Hostel_Building"])
        self.assertIn("CampusCamera", cols["Cameras"])
        self.assertIn("bb_court_surface", cols["Sports"])
        self.assertIn("campus_wall_wall", cols["Landscaping"])

    def test_most_specific_pattern_wins(self):
        bridge = Bridge()
        for name in ("hostel_walls", "hostel_furniture_wood"):
            bridge.create_object(name)
        SceneOrganizeTool(bridge).execute({"collections": {"Hostel_Building": ["hostel_*"],
                                                           "Furniture": ["hostel_furniture*"]}, "auto": False})
        self.assertEqual(bridge.collections["Furniture"], ["hostel_furniture_wood"])
        self.assertEqual(bridge.collections["Hostel_Building"], ["hostel_walls"])

    def test_organize_without_names_uses_standard_collections(self):
        bridge = Bridge()
        bridge.create_object("pine_tree_trunk")
        bridge.create_object("Sun", object_type="LIGHT")
        result = SceneOrganizeTool(bridge).execute({})
        self.assertTrue(result.success, result.error)
        self.assertEqual(set(result.data["collections"]), {"Landscaping", "Lighting"})   # no empty folders

    def test_save_goes_to_a_scenes_folder_with_the_asked_name(self):
        bridge = Bridge()
        with mock.patch.dict(os.environ, {"HOME": "/tmp/aiagent_home_test", "USERPROFILE": "/tmp/aiagent_home_test"}):
            result = SceneSaveTool(bridge).execute({"filename": "IIT_Hostel_Campus"})
        self.assertTrue(result.success, result.error)
        self.assertTrue(bridge.saved[0].endswith("IIT_Hostel_Campus.blend"), bridge.saved)

    def test_text_create_faces_a_point(self):
        bridge = Bridge()
        result = TextCreateTool(bridge).execute({"name": "board", "text": "MESS", "location": [0, -5, 3],
                                                 "face_towards": [0, 0]})
        self.assertTrue(result.success, result.error)
        self.assertAlmostEqual(abs(result.data["yaw_degrees"]) % 360, 180.0, places=0)


class TestCourtEquipment(unittest.TestCase):

    def setUp(self):
        fm.COURTS.clear()

    def test_courts_get_their_nets_and_hoops_and_no_duplicates(self):
        bridge = Bridge()
        result = FieldMarkingsTool(bridge).execute({"sport": "basketball", "name": "bb_court", "location": [25, 20, 0.02]})
        self.assertTrue(result.success, result.error)
        hoops = [e for e in result.data["equipment"] if e["model"] == "basketball_hoop"]
        self.assertEqual(sorted(e["location"] for e in hoops), [[10.0, 20.0], [40.0, 20.0]])
        self.assertIn("do not place them again", result.data["note"])
        before = len(bridge.get_objects())
        again = LibraryPlaceTool(bridge).execute({"model": "basketball_hoop", "location": [25, 20, 0]})
        self.assertTrue(again.success)
        self.assertTrue(again.data.get("skipped"))
        self.assertEqual(len(bridge.get_objects()), before)
        elsewhere = LibraryPlaceTool(bridge).execute({"model": "basketball_hoop", "location": [90, 90, 0]})
        self.assertFalse(elsewhere.data.get("skipped", False))

    def test_badminton_net_and_switch_off(self):
        bridge = Bridge()
        result = FieldMarkingsTool(bridge).execute({"sport": "badminton", "name": "bd", "location": [0, 0, 0.02]})
        self.assertEqual([e["model"] for e in result.data["equipment"]], ["badminton_net"])
        plain = FieldMarkingsTool(bridge).execute({"sport": "tennis", "name": "tn", "location": [40, 0, 0.02],
                                                   "equipment": False})
        self.assertNotIn("equipment", plain.data)

    def test_deleted_court_no_longer_blocks(self):
        bridge = Bridge()
        FieldMarkingsTool(bridge).execute({"sport": "badminton", "name": "bd", "location": [0, 0, 0.02]})
        bridge.delete_object("bd")
        result = LibraryPlaceTool(bridge).execute({"model": "badminton_net", "location": [0, 0, 0]})
        self.assertFalse(result.data.get("skipped", False))


class TestSmallFixes(unittest.TestCase):

    def test_material_recipe_without_name_gets_one(self):
        self.assertEqual(MaterialRecipeInput(recipe="grass", assign_to=["campus_ground"]).name, "campus_ground_grass")
        self.assertEqual(MaterialRecipeInput(recipe="concrete").name, "concrete_material")

    def test_cutaway_finds_buildings_and_frames_the_front(self):
        names = ["hostel_walls", "hostel_glass", "hostel_rooms", "hostel_structure", "tree"]
        self.assertEqual(building_cutaways(names), {"hostel": ["hostel_walls", "hostel_glass"]})
        self.assertEqual(building_cutaways(["wall", "tree"]), {})
        pose = cutaway_pose([-25, -25, 0], [25, 25, 20])
        self.assertLess(pose["location"][1], -25)               # in front of the building
        self.assertGreater(pose["target"][2], 0)

    def test_check_note_explains_the_cutaway(self):
        from blender_ai_agent.agent.post_verify import PostRunVerifier
        self.assertIn("cutaway", PostRunVerifier.RENDER_NOTE)


class TestChecksLeaveGeneratedPartsAlone(unittest.TestCase):

    def test_building_doors_are_not_a_giant_door(self):
        from blender_ai_agent.agent.scene_checks import assembly_parts, geometry_problems
        bridge = Bridge()
        MeshBuildingTool(bridge).execute({"name": "hostel", "shape": "U", "floors": 6})
        MeshBoundaryWallTool(bridge).execute({"name": "campus_wall", "size": [120, 120]})
        names = [o.name for o in bridge.get_objects()]
        parts = assembly_parts(names)
        self.assertIn("hostel_doors", parts)
        self.assertIn("campus_wall_cabin_door", parts)
        self.assertNotIn("Cube", assembly_parts(names + ["Cube"]))
        problems = geometry_problems(bridge, names)
        self.assertFalse([p for p in problems if "door" in p["where"]], problems)

    def test_grandstand_parts_count_as_one_assembly(self):
        from blender_ai_agent.agent.scene_checks import assembly_parts
        self.assertEqual(assembly_parts(["stand", "stand_seats", "stand_roof", "tree"]), {"stand", "stand_seats", "stand_roof"})

    def test_bare_path_gets_concrete_not_grass(self):
        from blender_ai_agent.agent.scene_checks import geometry_problems
        bridge = Bridge()
        bridge.create_mesh("main_path", [[-2, -20, 0], [2, -20, 0], [2, 20, 0], [-2, 20, 0]], [[0, 1, 2, 3]])
        fixes = [p["fix"] for p in geometry_problems(bridge, ["main_path"]) if p["where"] == "main_path"]
        if fixes:                                    # the fake bridge may not report materials at all
            self.assertIn("concrete", fixes[0])


class TestFraming(unittest.TestCase):

    def test_big_lawn_is_left_out_of_the_frame(self):
        from blender_ai_agent.tools.render_views import framing_box
        boxes = {"ground": {"min": [-70, -70, -0.01], "max": [70, 70, 0.0]},
                 "hostel": {"min": [-25, -25, 0], "max": [25, 25, 20]}}
        lo, hi = framing_box(boxes, [-70, -70, -0.01], [70, 70, 20])
        self.assertEqual((lo[0], hi[0]), (-25, 25))
        only_ground = framing_box({"ground": boxes["ground"]}, [-70, -70, -0.01], [70, 70, 0])
        self.assertEqual(only_ground[0][0], -70)


class TestTeamPlanTolerance(unittest.TestCase):

    def test_other_role_words_and_code_fences_are_understood(self):
        steps = parse_plan('```json\n{"steps": [{"role": "architect", "task": "build the hostel"},'
                           '{"role": "landscaping", "task": "garden"}, {"role": "cameras", "task": "two cameras"},]}\n```')
        self.assertEqual([s.role for s in steps], ["layout", "modeling", "lighting"])

    def test_unusable_plan_falls_back_to_the_sections_of_the_request(self):
        steps = fallback_plan(REQUEST)
        self.assertGreaterEqual(len(steps), 3)
        self.assertTrue(any(s.role == "finish" for s in steps))


class TestMustAct(unittest.TestCase):

    def test_fix_round_without_tool_calls_is_sent_back_to_work(self):
        loop, bridge, _ = build_repair_loop([
            ModelResponse(content="I have completed the fixes."),
            ModelResponse(tool_calls=[ToolCall("object.create", {"name": "bike_stand", "primitive": "CUBE"})]),
            ModelResponse(content="Added the bike stand."),
        ], max_iterations=6)
        result = loop.run("AUTOMATIC CHECK (round 1): MISSING - bicycle parking")
        self.assertIsNotNone(bridge.get_object("bike_stand"))
        self.assertEqual(result.reply_text, "Added the bike stand.")

    def test_normal_question_is_not_forced(self):
        loop, _bridge, _ = build_repair_loop([ModelResponse(content="A G+5 building has 6 storeys.")], max_iterations=3)
        result = loop.run("what does G+5 mean?")
        self.assertEqual(result.reply_text, "A G+5 building has 6 storeys.")

    def test_gives_up_after_two_nudges(self):
        loop, _bridge, _ = build_repair_loop([ModelResponse(content="done")] * 3, max_iterations=6)
        result = loop.run("AUTOMATIC CHECK (round 2): fix it")
        self.assertEqual(result.reply_text, "done")


class StepAgent:
    """Records each run; every run makes one successful tool call."""

    def __init__(self):
        self.messages, self.roles = [], []
        self.role_hint, self.tool_filter = "", None

    def run(self, message, state=None):
        self.messages.append(message)
        self.roles.append(self.role_hint)
        step = SimpleNamespace(tool_result=SimpleNamespace(success=True, data={}), tool_call=ToolCall("object.create", {"name": "x"}))
        return SimpleNamespace(reply_text="fixed", executed_steps=[step], task_id="t", rolled_back=False, stopped_reason="stop")


class FixPlanner:
    def __init__(self, steps):
        self.steps, self.requests = steps, []

    def plan(self, request):
        self.requests.append(request)
        return [TeamStep(role, task) for role, task in self.steps]


class TestTeamFix(unittest.TestCase):

    def report(self, score, missing):
        return SimpleNamespace(score=score, missing=missing)

    def test_far_off_result_is_fixed_in_planned_steps(self):
        agent = StepAgent()
        planner = FixPlanner([("modeling", "build the bicycle parking"), ("finish", "organise collections")])
        controller = CopilotController(agent, auto_split=False, team_planner=planner)
        result = controller._run_fix("AUTOMATIC CHECK (round 1): ...", self.report(2.0, ["a", "b", "c"]), 0)
        self.assertTrue(result.success)
        self.assertEqual(len(agent.messages), 2)
        self.assertTrue(agent.messages[0].startswith("AUTOMATIC CHECK fix step 1/2: build the bicycle parking"))
        self.assertTrue(agent.roles[0])                          # each step runs with its role brief
        self.assertEqual(agent.role_hint, "")                    # and the role is cleared afterwards
        self.assertEqual(controller._last_tool_calls, 2)

    def test_small_fix_stays_one_agent_run(self):
        agent = StepAgent()
        planner = FixPlanner([("modeling", "a"), ("modeling", "b")])
        controller = CopilotController(agent, auto_split=False, team_planner=planner)
        controller._run_fix("AUTOMATIC CHECK (round 1): ...", self.report(8.0, ["a"]), 0)
        self.assertEqual(planner.requests, [])
        self.assertEqual(len(agent.messages), 1)

    def test_idle_round_also_replans(self):
        agent = StepAgent()
        planner = FixPlanner([("modeling", "a"), ("lighting", "b")])
        controller = CopilotController(agent, auto_split=False, team_planner=planner)
        controller._run_fix("AUTOMATIC CHECK (round 3): ...", self.report(8.0, []), 1)
        self.assertEqual(len(planner.requests), 1)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestClaude(unittest.TestCase):

    def test_tool_names_round_trip(self):
        self.assertEqual(to_claude_name("mesh.building"), "mesh__building")
        self.assertEqual(from_claude_name("mesh__building"), "mesh.building")
        self.assertEqual(from_claude_name("x", {"x": "a.b"}), "a.b")

    def test_messages_alternate_and_start_and_end_with_user(self):
        system, messages = claude_messages([
            Message("system", "rules"), Message("system", "scene"), Message("assistant", "hi"),
            Message("user", "build"), Message("tool", "ok"), Message("assistant", "")])
        self.assertEqual(system, "rules\n\nscene")
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user"])
        self.assertIn("[Tool result] ok", messages[-1]["content"])

    def test_request_and_tool_call_reply(self):
        seen = {}

        def fake(request, timeout=None):
            seen["body"] = json.loads(request.data)
            seen["key"] = request.get_header("X-api-key")
            seen["version"] = request.get_header("Anthropic-version")
            return _Response(json.dumps({"content": [
                {"type": "text", "text": "Building it."},
                {"type": "tool_use", "id": "t1", "name": "mesh__building", "input": {"floors": 6}}],
                "stop_reason": "tool_use", "usage": {"input_tokens": 10, "output_tokens": 4}}).encode())

        tools = [ToolDefinition("mesh.building", "Builds a building",
                                {"type": "object", "properties": {"floors": {"type": "integer"}}})]
        with mock.patch("blender_ai_agent.net.urlopen", fake):
            reply = ClaudeProvider("KEY", "claude-sonnet-5-5").generate(
                ModelRequest(messages=[Message("system", "be good"), Message("user", "hostel")], tools=tools))
        body = seen["body"]
        self.assertEqual((seen["key"], seen["version"]), ("KEY", "2023-06-01"))
        self.assertEqual(body["model"], "claude-sonnet-5-5")
        self.assertEqual(body["system"], "be good")
        self.assertEqual(body["tools"][0]["name"], "mesh__building")
        self.assertEqual(body["tools"][0]["input_schema"]["type"], "object")
        self.assertEqual(reply.tool_calls[0].tool_name, "mesh.building")
        self.assertEqual(reply.tool_calls[0].arguments, {"floors": 6})
        self.assertEqual(reply.content, "Building it.")
        self.assertEqual(reply.usage.completion_tokens, 4)

    def http_error(self, code, message, headers=None):
        body = json.dumps({"type": "error", "error": {"type": "x", "message": message}}).encode()

        def fake(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, code, "err", headers or {}, io.BytesIO(body))
        return fake

    def test_errors_are_explained(self):
        provider = ClaudeProvider("KEY")
        provider.RETRIES = 0
        request = ModelRequest(messages=[Message("user", "hi")])
        for code, message, expect in ((401, "invalid x-api-key", "not valid"),
                                      (400, "Your credit balance is too low", "credit"),
                                      (429, "rate limited", "429")):
            with mock.patch("blender_ai_agent.net.urlopen", self.http_error(code, message)):
                with self.assertRaises(RuntimeError) as caught:
                    provider.generate(request)
            self.assertIn(expect, str(caught.exception))

    def test_overloaded_is_retried(self):
        calls = []
        ok = json.dumps({"content": [{"type": "text", "text": "hello"}]}).encode()

        def fake(request, timeout=None):
            calls.append(1)
            if len(calls) == 1:
                raise urllib.error.HTTPError(request.full_url, 529, "overloaded", {"retry-after": "0"},
                                             io.BytesIO(b"{}"))
            return _Response(ok)

        with mock.patch("blender_ai_agent.net.urlopen", fake), mock.patch("time.sleep"):
            reply = ClaudeProvider("KEY").generate(ModelRequest(messages=[Message("user", "hi")]))
        self.assertEqual((len(calls), reply.content), (2, "hello"))

    def test_vision_client_sends_images(self):
        seen = {}

        def fake(request, timeout=None):
            seen["body"] = json.loads(request.data)
            return _Response(json.dumps({"content": [{"type": "text", "text": '{"score": 9}'}]}).encode())

        client = ClaudeVisionClient(sc.BuilderConfig(api_key="KEY", vision_provider="claude"))
        with mock.patch("blender_ai_agent.net.urlopen", fake):
            text = client.generate("review", [{"text": "view front"},
                                              {"inline_data": {"mime_type": "image/png", "data": "AAAA"}}], json_mode=True)
        self.assertEqual(text, '{"score": 9}')
        content = seen["body"]["messages"][0]["content"]
        self.assertEqual(content[1]["type"], "image")
        self.assertEqual(content[1]["source"]["media_type"], "image/png")

    def test_vision_follows_the_chosen_ai(self):
        env = {"GEMINI_API_KEY": "g", "ANTHROPIC_API_KEY": "c", "BLENDER_AI_ACTIVE_PROVIDER": "claude"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("BLENDER_AI_VISION", None)
            cfg = sc.load_builder_config("/nonexistent.json")
            self.assertEqual((cfg.vision_provider, cfg.api_key), ("claude", "c"))
            self.assertIsInstance(sc.make_vision_client(cfg), ClaudeVisionClient)
            os.environ["BLENDER_AI_ACTIVE_PROVIDER"] = "gemini"
            cfg = sc.load_builder_config("/nonexistent.json")
            self.assertEqual((cfg.vision_provider, cfg.api_key), ("gemini", "g"))
            self.assertIsInstance(sc.make_vision_client(cfg), sc.GeminiClient)
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "c", "BLENDER_AI_ACTIVE_PROVIDER": "groq"}):
            for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "BLENDER_AI_VISION"):
                os.environ.pop(k, None)
            cfg = sc.load_builder_config("/nonexistent.json")
            self.assertEqual((cfg.vision_provider, cfg.api_key), ("claude", "c"))   # only a Claude key: Claude looks

    def test_registered_with_a_key(self):
        import blender_ai_agent as addon
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "c"}):
            addon.reset_providers()
            try:
                registry = addon.get_provider_registry()
                self.assertIn("claude", registry.list_providers())
                provider = registry.create("claude", model_name="claude-opus-5-5")
                self.assertEqual(provider.model_name, "claude-opus-5-5")
            finally:
                addon.reset_providers()


if __name__ == "__main__":
    unittest.main()
