"""The redesigned panel's pure-Python parts: recent tasks, quick prompts, scene context, Ctrl+V recovery,
the checkpoint / revert fallback, API keys from add-on preferences and the SDK-free Gemini REST path."""

from . import _bpy_stub  # noqa: F401

import io
import json
import os
import tempfile
import unittest
import urllib.error
from unittest import mock

from blender_ai_agent import prefs
from blender_ai_agent.providers.gemini_provider import GeminiProvider, RestGeminiModel
from blender_ai_agent.ui import run_state
from blender_ai_agent.ui.panel import recover_cut_paste
from .fakes import FakeBridge


class TestRecentTasks(unittest.TestCase):

    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "recent.json")

    def test_round_trip_and_newest_first(self):
        tasks = run_state.add_task([], "make a chair", "Done 3/3 steps.\nAll good", True, 12.34)
        tasks = run_state.add_task(tasks, "make a table", "Done", True, 5)
        run_state.save_recent(tasks, self.path)
        loaded = run_state.load_recent(self.path)
        self.assertEqual([t["prompt"] for t in loaded], ["make a table", "make a chair"])
        self.assertEqual(loaded[1]["seconds"], 12.3)

    def test_same_prompt_is_not_listed_twice(self):
        tasks = run_state.add_task([], "court", "Done", True, 1)
        tasks = run_state.add_task(tasks, "court", "Done", True, 2)
        self.assertEqual(len(tasks), 1)

    def test_list_is_capped(self):
        tasks = []
        for i in range(30):
            tasks = run_state.add_task(tasks, f"p{i}", "Done", True, 1)
        self.assertEqual(len(tasks), run_state.MAX_RECENT)

    def test_broken_file_gives_empty_list(self):
        with open(self.path, "w") as handle:
            handle.write("{not json")
        self.assertEqual(run_state.load_recent(self.path), [])
        self.assertEqual(run_state.load_recent(self.path + ".missing"), [])

    def test_classify(self):
        self.assertEqual(run_state.classify("Stopped by user", False), "stopped")
        self.assertEqual(run_state.classify("Done 2/5 steps", True), "partial")
        self.assertEqual(run_state.classify("Done 0/5 steps", True), "failed")
        self.assertEqual(run_state.classify("Done 5/5 steps", True), "completed")
        self.assertEqual(run_state.classify("oops", False), "failed")

    def test_check_line(self):
        reply = "Done\nAuto-check ✓ fixed after 2 round(s): vision 7/10 -> vision 10/10"
        self.assertEqual(run_state.check_line(reply), "Auto-check: vision 10/10, 2 fix round(s)")
        self.assertEqual(run_state.check_line("no check here"), "")

    def test_title_is_shortened(self):
        self.assertEqual(run_state.title("\n - short\nmore"), "short")
        long = run_state.title("x" * 80, width=20)
        self.assertEqual(len(long), 20)
        self.assertTrue(long.endswith("…"))


class TestQuickAndContext(unittest.TestCase):

    def test_quick_prompt_names_selection_or_whole_scene(self):
        self.assertIn("Chair, Table", run_state.quick_prompt("MATERIAL", ["Chair", "Table"]))
        self.assertIn("every object", run_state.quick_prompt("LIGHTING", []))
        many = run_state.quick_prompt("MODELING", [f"o{i}" for i in range(12)])
        self.assertIn("+4 more", many)

    def test_scene_context_only_when_something_is_selected(self):
        self.assertEqual(run_state.with_scene_context("make it red", [], None), "make it red")
        text = run_state.with_scene_context("make it red", ["Cube"], "Cube")
        self.assertIn("selected objects: Cube; active: Cube", text)
        self.assertTrue(text.startswith("make it red\n(Scene context:"))

    def test_big_request_ignores_scene_context(self):
        from blender_ai_agent.multi_agent.team import is_big_request
        small = run_state.with_scene_context("make it red", [f"stadium_part_{i}" for i in range(12)], None)
        self.assertFalse(is_big_request(small))


class TestPaste(unittest.TestCase):

    def test_first_line_paste_becomes_whole_clipboard(self):
        clip = "Build a badminton court\n- 2 rackets\n- a bench"
        self.assertEqual(recover_cut_paste("Build a badminton court", clip), clip)

    def test_typed_text_is_left_alone(self):
        self.assertEqual(recover_cut_paste("make a cup", "Build a court\nwith lines"), "make a cup")
        self.assertEqual(recover_cut_paste("make a cup", "one line"), "make a cup")
        self.assertEqual(recover_cut_paste("", "a\nb"), "")


class TestCheckpoint(unittest.TestCase):

    def test_full_checkpoint_uses_bridge_restore(self):
        class Bridge(FakeBridge):
            def save_checkpoint(self, path):
                return {"objects": ["Cube"]}

            def restore_checkpoint(self, path, info):
                return {"restored": info["objects"]}

        bridge = Bridge()
        self.assertEqual(run_state.take_checkpoint(bridge, "p"), "full")
        self.assertTrue(run_state.has_checkpoint())
        self.assertEqual(run_state.checkpoint_prompt(), "p")
        self.assertIn("1 objects", run_state.revert(bridge))
        self.assertFalse(run_state.has_checkpoint())
        self.assertEqual(run_state.revert(bridge), "Nothing to revert.")

    def test_basic_fallback_removes_new_objects(self):
        bridge = FakeBridge()
        bridge.create_object("Old")
        if hasattr(bridge, "save_checkpoint"):
            bridge.save_checkpoint = None
        self.assertEqual(run_state.take_checkpoint(bridge, "p"), "basic")
        bridge.create_object("New")
        message = run_state.revert(bridge)
        self.assertIn("Reverted", message)
        self.assertIsNotNone(bridge.get_object("Old"))
        self.assertIsNone(bridge.get_object("New"))

    def test_failed_full_save_falls_back(self):
        class Bridge(FakeBridge):
            def save_checkpoint(self, path):
                raise RuntimeError("no libraries.write here")

        self.assertEqual(run_state.take_checkpoint(Bridge(), "p"), "basic")


class TestPrefsKeys(unittest.TestCase):

    def tearDown(self):
        for _prop, env, _l, _u in prefs.KEYS:
            if prefs._applied.pop(env, None) is not None:
                os.environ.pop(env, None)

    def test_key_from_preferences_reaches_environment_and_can_be_cleared(self):
        class P:
            gemini_api_key = "  abc123  "
            groq_api_key = ""
            openai_api_key = ""

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GEMINI_API_KEY", None)
            p = P()
            prefs.apply_keys(p)
            self.assertEqual(os.environ.get("GEMINI_API_KEY"), "abc123")
            self.assertTrue(prefs.has_key("gemini"))
            p.gemini_api_key = ""
            prefs.apply_keys(p)
            self.assertNotIn("GEMINI_API_KEY", os.environ)

    def test_clearing_does_not_remove_a_key_set_outside_blender(self):
        class P:
            gemini_api_key = groq_api_key = openai_api_key = ""

        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "from-shell"}):
            prefs.apply_keys(P())
            self.assertEqual(os.environ["GROQ_API_KEY"], "from-shell")

    def test_panel_picks_up_a_saved_key_late(self):
        from blender_ai_agent.ui import panel

        class P:
            gemini_api_key, openai_api_key, claude_api_key = "", "sk-late", ""

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("OPENAI_API_KEY", None)
            with mock.patch.object(prefs, "get_prefs", return_value=P()):
                self.assertTrue(panel._has_key("openai"))
            self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-late")

    def test_no_prefs_is_harmless(self):
        prefs.apply_keys(None)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestGeminiRest(unittest.TestCase):

    def test_request_and_reply(self):
        seen = {}

        def fake_urlopen(request, timeout=None):
            seen["url"], seen["body"] = request.full_url, json.loads(request.data)
            seen["key"] = request.get_header("X-goog-api-key")
            return _Response(json.dumps({"candidates": [{"content": {"parts": [
                {"text": "hi"}, {"functionCall": {"name": "object.create", "args": {"name": "Cube"}}}]}}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2}}).encode())

        with mock.patch("blender_ai_agent.net.urlopen", fake_urlopen):
            data = RestGeminiModel("KEY", "gemini-2.5-flash", tools=[{"x": 1}]).generate_content([{"role": "user"}])
        self.assertIn("gemini-2.5-flash:generateContent", seen["url"])
        self.assertEqual(seen["key"], "KEY")
        self.assertEqual(seen["body"]["tools"], [{"x": 1}])
        reply = GeminiProvider._parse_rest_response(data)
        self.assertEqual(reply.content, "hi")
        self.assertEqual(reply.tool_calls[0].tool_name, "object.create")
        self.assertEqual(reply.tool_calls[0].arguments, {"name": "Cube"})
        self.assertEqual(reply.finish_reason, "tool_calls")
        self.assertEqual(reply.usage.prompt_tokens, 5)

    def test_quota_error_keeps_retry_wording(self):
        body = json.dumps({"error": {"message": "Quota exceeded", "details": [{"retryDelay": "31s"}]}}).encode()

        def fake_urlopen(request, timeout=None):
            raise urllib.error.HTTPError(request.full_url, 429, "Too Many", {}, io.BytesIO(body))

        with mock.patch("blender_ai_agent.net.urlopen", fake_urlopen):
            with self.assertRaises(RuntimeError) as caught:
                RestGeminiModel("KEY", "m").generate_content([])
        self.assertEqual(str(caught.exception), "429 Quota exceeded Please retry in 31s.")

    def test_blocked_prompt_message(self):
        reply = GeminiProvider._parse_rest_response({"promptFeedback": {"blockReason": "SAFETY"}})
        self.assertIn("SAFETY", reply.content)
        self.assertEqual(reply.tool_calls, [])


if __name__ == "__main__":
    unittest.main()
