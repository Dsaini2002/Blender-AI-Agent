"""15 Nov: the AI reads the request first (checklist, tools, missing tools, save), places the things, the deep check
looks from every angle; only the picked provider is used and a used-up quota is waited out; the review's P0/P1 bugs."""

from . import _bpy_stub  # noqa: F401

import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent.agent import arrange, checklist, understand
from blender_ai_agent.agent.self_correct import parse_critique
from blender_ai_agent.copilot.quota_wait import QuotaWaiter, wait_seconds_from


def defs(*names):
    return [SimpleNamespace(name=n, description=f"{n} tool", parameters={}) for n in names]


class UnderstandTest(unittest.TestCase):

    ANSWER = json.dumps({
        "kind": "new", "summary": "table with books",
        "checklist": [{"item": "Table", "count": 1, "position": ""},
                      {"item": "book", "count": "2", "position": "on the table", "size": "0.24 x 0.17 x 0.03 m"}],
        "tools": ["object.create", "made.up.tool", "scene.save"],
        "missing": [{"what": "laptop hinge", "how": "mesh.create"}],
        "save": {"wanted": True, "filename": "desk"}})

    def test_ai_plan_is_read(self):
        result = understand.understand(lambda s, u: "```json\n" + self.ANSWER + "\n```", "table with two books",
                                       defs("object.create", "scene.save", "python.execute"))
        self.assertEqual(result.source, "ai")
        self.assertEqual([(i.name, i.count, i.position) for i in result.checklist],
                         [("table", 1, ""), ("book", 2, "on the table")])
        self.assertEqual(result.checklist[1].size, "0.24 x 0.17 x 0.03 m")
        self.assertEqual(result.tools, ["object.create", "scene.save"])            # unknown tool dropped
        self.assertEqual(result.filename, "desk.blend")
        tools = result.tool_set({"object.create", "scene.save", "python.execute", "object.measure", "mesh.create"})
        self.assertIn("python.execute", tools)                                        # a missing part -> maker tools
        self.assertIn("object.measure", tools)                                        # core always
        self.assertIn("laptop hinge -> mesh.create", result.builder_note())
        self.assertIn("scene.save(filename='desk.blend')", result.builder_note())

    def test_unreadable_answer_falls_back_to_the_rules(self):
        result = understand.understand(lambda s, u: "sorry", "create a table with two books, save it",
                                       defs("object.create"))
        self.assertEqual(result.source, "rules")
        self.assertEqual([(i.noun, i.count) for i in result.checklist], [("table", 1), ("book", 2)])
        self.assertTrue(result.save_wanted)
        self.assertEqual(result.tool_set(), set())                                    # keyword tool rules stay

    def test_rules_checklist(self):
        items = checklist.make_checklist("create a table with two books and a laptop, and a lamp")
        self.assertEqual([(i.noun, i.count, i.position) for i in items],
                         [("table", 1, ""), ("book", 2, "on the table"), ("laptop", 1, "on the table"), ("lamp", 1, "")])
        items = checklist.make_checklist("add 3 chairs around a round dining table and a chandelier above it")
        self.assertEqual([i.noun for i in items], ["chair", "dining_table", "chandelier"])
        self.assertEqual(items[2].position, "above the round dining table")
        self.assertEqual(checklist.make_checklist("change the colour of the sofa"), [])
        car = checklist.make_checklist("a car at (2, 3, 0) and two trees behind it")
        self.assertEqual(car[0].position.replace(" ", ""), "at(230)")


class ArrangeTest(unittest.TestCase):

    def snapshot(self, objects):
        return {"objects": [{"name": n, "type": "MESH", "box": {"min": lo, "max": hi}, "hidden": False,
                             "materials": ["m"], "location": [0, 0, 0], "rotation": [0, 0, 0], "scale": [1, 1, 1]}
                            for n, lo, hi in objects]}

    def test_things_go_where_the_ai_says_and_bad_moves_are_undone(self):
        boxes = {"table_top": [[-0.6, -0.4, 0.73], [0.6, 0.4, 0.78]], "book_1": [[-2.1, 0.9, 0], [-1.9, 1.1, 0.03]],
                 "book_2": [[3, 3, 0], [3.2, 3.2, 0.03]]}
        moved = {}

        class Bridge:
            def scene_snapshot(self):
                return ArrangeTest.snapshot(None, [(n, b[0], b[1]) for n, b in boxes.items()])

            def get_object(self, name):
                box = boxes[name]
                centre = [(box[0][k] + box[1][k]) / 2 for k in range(3)]
                return SimpleNamespace(name=name, location=centre, rotation_euler=[0, 0, 0], parent=None)

            def transform_object(self, name, location=None, rotation=None):
                box = boxes[name]
                centre = [(box[0][k] + box[1][k]) / 2 for k in range(3)]
                delta = [location[k] - centre[k] for k in range(3)]
                boxes[name] = [[box[0][k] + delta[k] for k in range(3)], [box[1][k] + delta[k] for k in range(3)]]
                moved[name] = location
                return True

        items = [checklist.Item("table", 1, "table", words=["table"]),
                 checklist.Item("book", 2, "book", position="on the table", words=["book"])]
        asked = {}

        def ask(system, user):
            asked["user"] = user
            return json.dumps({"placements": [{"thing": "book_1", "location": [-0.3, 0, 0.78]},
                                              {"thing": "book_2", "location": [0.3, 0, 0.78], "turn_degrees": 0}]})
        with mock.patch("blender_ai_agent.diagnostics.scene_audit._library_parts", return_value={}):
            result = arrange.Arranger(Bridge(), ask).arrange("table with two books", items,
                                                             new_objects={"table_top", "book_1", "book_2"})
        self.assertIn('user said: "on the table"', asked["user"])
        self.assertEqual(sorted(result.moved), ["book_1", "book_2"])
        self.assertAlmostEqual(boxes["book_1"][0][2], 0.78, places=3)                 # bottom on the table top
        self.assertFalse(result.undone)

        # a move that makes the scene worse is undone
        def bad(system, user):
            return json.dumps({"placements": [{"thing": "book_1", "location": [0.0, 0.0, 0.5]}]})   # inside the table
        before = [list(v) for v in boxes["book_1"]]
        with mock.patch("blender_ai_agent.diagnostics.scene_audit._library_parts", return_value={}), \
                mock.patch.object(arrange, "_high_count", side_effect=[0, 2]):
            result = arrange.Arranger(Bridge(), bad).arrange("table with two books", items,
                                                             new_objects={"table_top", "book_1", "book_2"})
        self.assertTrue(result.undone)
        self.assertEqual(boxes["book_1"], before)


class DeepReviewParseTest(unittest.TestCase):

    def test_counts_places_and_measured_lines(self):
        text = json.dumps({"score": 6, "summary": "", "problems": [],
                           "checklist": [{"item": "book", "wanted": 2, "seen": 1, "present": True, "where_ok": True},
                                         {"item": "laptop", "wanted": 1, "seen": 1, "present": True, "where_ok": False,
                                          "issue": "floats above the table"},
                                         {"item": "lamp", "wanted": 1, "seen": 0, "present": False}],
                           "measured": [{"line": 1, "real": True}, {"line": 2, "real": False}]})
        critique = parse_critique(text, ["[high] 'desk' floats 0.70 m", "[medium] 'rug' sunk"])
        self.assertIn("book (1 of 2 seen - 1 more needed)", critique.missing)
        self.assertIn("lamp", critique.missing)
        issues = [p["issue"] for p in critique.problems]
        self.assertIn("floats above the table", issues)
        self.assertIn("[high] 'desk' floats 0.70 m", issues)
        self.assertNotIn("[medium] 'rug' sunk", issues)


class QuotaWaitTest(unittest.TestCase):

    def test_wait_times(self):
        self.assertEqual(wait_seconds_from("429 ... Please retry in 43744.2s."), 43744.2)
        self.assertEqual(wait_seconds_from("Rate limit ... Please try again in 1m30s"), 90)
        self.assertIsNone(wait_seconds_from("429 quota"))

    def test_waits_with_countdown_then_goes_on(self):
        now = [0.0]
        shown = []
        waiter = QuotaWaiter("Gemini", status=shown.append, clock=lambda: now[0],
                             sleep=lambda s: now.__setitem__(0, now[0] + s))
        self.assertTrue(waiter.wait("429 quota (retry in 100s)"))
        self.assertGreaterEqual(now[0], 105)
        self.assertTrue(any("resumes in" in s for s in shown))
        self.assertTrue(waiter.wait("429 quota"))                                       # no time given: probes
        self.assertAlmostEqual(waiter.total_waited, 105 + 120, delta=1)

    def test_waiting_cannot_fix_a_bad_key(self):
        waiter = QuotaWaiter("Gemini", sleep=lambda s: None)
        self.assertFalse(waiter.wait("401 invalid api key"))


class ReviewBugsTest(unittest.TestCase):

    def test_openai_uses_the_responses_api_with_mapped_tool_names(self):
        from blender_ai_agent.agent.models import Message
        from blender_ai_agent.providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider("k")
        self.assertTrue(provider.API_URL.endswith("/v1/responses"))      # GPT-6 Astra: tools only on Responses
        tools = provider._build_tools(defs("object.create", "mesh.building"))
        self.assertEqual([t["name"] for t in tools], ["object__create", "mesh__building"])
        self.assertEqual(tools[0]["type"], "function")
        instructions, items = provider._build_input([Message("system", "rules"), Message("user", "make a cube"),
                                                     Message("assistant", ""), Message("tool", "ok")])
        self.assertEqual(instructions, "rules")
        self.assertEqual(items, [{"role": "user", "content": "make a cube"},
                                 {"role": "user", "content": "[Tool result] ok"}])
        reply = provider._parse_response({"status": "completed", "output": [
            {"type": "reasoning", "summary": []},
            {"type": "function_call", "name": "mesh__building", "arguments": "{\"floors\": 3}", "call_id": "c1"},
            {"type": "message", "content": [{"type": "output_text", "text": "building it"}]}],
            "usage": {"input_tokens": 9000, "output_tokens": 700, "output_tokens_details": {"reasoning_tokens": 500}}})
        self.assertEqual(reply.tool_calls[0].tool_name, "mesh.building")
        self.assertEqual(reply.tool_calls[0].arguments, {"floors": 3})
        self.assertEqual((reply.usage.prompt_tokens, reply.usage.completion_tokens), (9000, 700))
        self.assertEqual(reply.content, "building it")

    def test_openai_thinking_without_an_answer_is_said(self):
        from blender_ai_agent.providers.openai_provider import OpenAIProvider
        with self.assertRaises(RuntimeError) as caught:
            OpenAIProvider("k")._parse_response({"status": "incomplete", "output": [{"type": "reasoning"}],
                                                 "incomplete_details": {"reason": "max_output_tokens"},
                                                 "usage": {"input_tokens": 9000, "output_tokens": 16000,
                                                           "output_tokens_details": {"reasoning_tokens": 16000}}})
        self.assertIn("max_output_tokens", str(caught.exception))
        self.assertIn("16,000 reasoning", str(caught.exception))

    def test_openai_payload_has_no_temperature_and_low_reasoning(self):
        from blender_ai_agent.agent.models import Message, ModelRequest
        from blender_ai_agent.providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider("k")
        sent = {}
        provider._call_api = lambda payload: sent.update(payload) or {"status": "completed", "output": []}
        provider.generate(ModelRequest(messages=[Message("user", "hi")], tools=defs("object.create"), temperature=0.2))
        self.assertNotIn("temperature", sent)
        self.assertEqual(sent["reasoning"], {"effort": "low"})
        self.assertEqual(sent["tools"][0]["name"], "object__create")

    def test_python_tool_runs_on_the_main_thread(self):
        from blender_ai_agent.tools import python_power_tool as pp
        calls = []
        with mock.patch("blender_ai_agent.bridge.main_thread_dispatch.run_on_main_thread",
                        side_effect=lambda f: calls.append(f) or f()):
            pp.PythonPowerTool(SimpleNamespace(get_objects=lambda: [])).run(
                pp.PythonExecutionInput(code="x = 1"))
        self.assertEqual(len(calls), 2)                     # the snapshot + the code itself

    def test_rollback_renames_back_instead_of_deleting(self):
        from blender_ai_agent.reliability.rollback import RollbackManager
        from blender_ai_agent.reliability.snapshot import ObjectSnapshot, SceneSnapshot

        class Obj(SimpleNamespace):
            pass
        scene = {"Table": Obj(name="Table", session_uid=7, location=[0, 0, 0]),
                 "New": Obj(name="New", session_uid=9, location=[0, 0, 0])}
        log = []

        class Bridge:
            def get_objects(self):
                return list(scene.values())

            def delete_object(self, name):
                log.append(("delete", name))
                scene.pop(name)

            def rename_object(self, old, new):
                log.append(("rename", old, new))
                obj = scene.pop(old)
                obj.name = new
                scene[new] = obj

            def transform_object(self, *a, **k):
                return True
        snap = SceneSnapshot([ObjectSnapshot("Keep", "MESH", [0, 0, 0], [0, 0, 0], [1, 1, 1], uid=7)])
        RollbackManager(Bridge()).rollback_to(snap)
        self.assertIn(("rename", "Table", "Keep"), log)
        self.assertNotIn(("delete", "Table"), log)
        self.assertIn(("delete", "New"), log)

    def test_save_after_a_change_is_not_skipped(self):
        from blender_ai_agent.agent.models import ToolCall
        from blender_ai_agent.agent.repair_loop import RepairableExecutionLoop
        loop = RepairableExecutionLoop.__new__(RepairableExecutionLoop)
        loop._revision = 1
        save = ToolCall(tool_name="scene.save", arguments={"filename": "a.blend"})
        create = ToolCall(tool_name="object.create", arguments={"name": "x"})
        done = {loop._call_key(save): 1, loop._call_key(create): 1}
        loop.MAX_RENDERS_PER_RUN = 3
        self.assertIsNotNone(loop._skip_reason(save, done, 0))        # nothing changed since: a repeat
        loop._revision = 2                                             # the scene changed after the save
        self.assertIsNone(loop._skip_reason(save, done, 0))           # -> save again
        self.assertIsNotNone(loop._skip_reason(create, done, 0))      # a repeated create is still skipped

    def test_save_is_never_hidden(self):
        from blender_ai_agent.agent.tool_selection import select_tools, wants_save
        chosen = [d.name for d in select_tools(defs("scene.save", "scene.organize", "object.create"),
                                               "ghar bana kar file bana do")]
        self.assertIn("scene.save", chosen)
        self.assertTrue(wants_save("ghar bana kar file bana do"))

    def test_saved_file_is_checked_on_disk(self):
        from blender_ai_agent.tools.site_tools import verify_saved_file
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "a.blend")
            self.assertIn("no file", verify_saved_file(path))
            with open(path, "wb") as handle:
                handle.write(b"BLENDER-v500" + b"\0" * 4000)
            self.assertEqual(verify_saved_file(path), "")
            with open(path, "wb") as handle:
                handle.write(b"x" * 4000)
            self.assertIn("not a .blend", verify_saved_file(path))

    def test_honest_status(self):
        from blender_ai_agent.copilot.controller import CopilotController
        controller = CopilotController.__new__(CopilotController)
        ok = SimpleNamespace(tool_call=SimpleNamespace(tool_name="object.create"), tool_result=SimpleNamespace(success=True))
        look = SimpleNamespace(tool_call=SimpleNamespace(tool_name="scene.inspect"),
                               tool_result=SimpleNamespace(success=True))
        run = SimpleNamespace(stopped_reason="stop", executed_steps=[look])
        self.assertEqual(controller._run_status("make a table", run, [look]), "failed")       # zero-tool "Done"
        self.assertEqual(controller._run_status("what is in my scene?", run, [look]), "completed")
        self.assertEqual(controller._run_status("make a table", run, [ok]), "completed")
        limit = SimpleNamespace(stopped_reason="max_iterations_reached", executed_steps=[ok])
        self.assertEqual(controller._run_status("make a table", limit, [ok]), "partial")

    def test_skill_leftover(self):
        from blender_ai_agent.copilot.controller import CopilotController
        controller = CopilotController.__new__(CopilotController)
        self.assertEqual(controller._skill_leftover("make a house and save it as home.blend"), "save the file")
        self.assertEqual(controller._skill_leftover("make a house"), "")


if __name__ == "__main__":
    unittest.main()
