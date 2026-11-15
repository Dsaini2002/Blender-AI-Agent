"""15 Nov: Stop must stop at once (not after the current AI answer / render), and a missing API key is said plainly."""

from . import _bpy_stub  # noqa: F401

import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent import net
from blender_ai_agent.copilot import activity


class StopNowTest(unittest.TestCase):

    def tearDown(self):
        activity.end_run()
        activity.run_thread_ended()

    def test_stop_ends_the_wait_for_the_ai_at_once(self):
        activity.begin_run()
        result = {}

        def slow(request, timeout):
            time.sleep(30)                                  # the AI takes long to answer
            return "late answer"

        def ask():
            started = time.time()
            try:
                net.urlopen("req", 120)
            except RuntimeError as exc:
                result["error"] = str(exc)
            result["seconds"] = time.time() - started
        with mock.patch.object(net, "_urlopen", slow):
            worker = threading.Thread(target=ask)
            worker.start()
            time.sleep(0.4)
            activity.abandon()                              # the user pressed Stop
            worker.join(3)
        self.assertIn("Stopped by user", result["error"])
        self.assertLess(result["seconds"], 1.5)

    def test_after_stop_no_tool_changes_the_scene(self):
        from blender_ai_agent.agent.models import ToolCall
        from blender_ai_agent.agent.tool_caller import ToolCaller
        ran = []
        tool = SimpleNamespace(name="object.create", execute=lambda args: ran.append(args))
        caller = ToolCaller(SimpleNamespace(get=lambda n: tool, list_tools=lambda: ["object.create"]))
        activity.begin_run()
        activity.abandon()
        activity.end_run()                                  # the panel already finished the run
        result = caller.call(ToolCall(tool_name="object.create", arguments={"name": "x"}))
        self.assertFalse(result.success)
        self.assertIn("Stopped by user", result.error)
        self.assertEqual(ran, [])
        activity.run_thread_ended()                         # the old run's thread is gone
        self.assertFalse(activity.should_stop())            # other buttons work again

    def test_no_run_no_thread(self):
        with mock.patch.object(net, "_urlopen", return_value="ok") as direct:
            self.assertEqual(net.urlopen("req", 5), "ok")
        direct.assert_called_once()


class NoKeyTest(unittest.TestCase):

    def test_panel_says_the_key_is_missing(self):
        from blender_ai_agent.ui import panel
        layout = mock.MagicMock()
        for name in ("row", "column", "box"):
            getattr(layout, name).return_value = layout
        scene = SimpleNamespace(aiagent_provider_choice="claude", aiagent_copilot_input="make a table",
                                aiagent_prompt_lines=[], aiagent_is_running=False, aiagent_show_settings=False,
                                aiagent_change_key=False, aiagent_scene_context=True, aiagent_last_reply="",
                                aiagent_claude_model_choice="claude-sonnet-5-5", aiagent_key_input="")
        with mock.patch.object(panel, "_has_key", return_value=False):
            texts = []
            layout.label.side_effect = lambda **k: texts.append(k.get("text", ""))
            context = SimpleNamespace(scene=scene, region=SimpleNamespace(width=400), preferences=None,
                                      selected_objects=[], active_object=None, window_manager=None)
            panel.AIAgentPanel._draw_body(SimpleNamespace(layout=layout, _draw_settings=lambda *a, **k: None,
                                                          _draw_result=lambda *a, **k: None,
                                                          _draw_recent=lambda *a, **k: None,
                                                          _draw_live=lambda *a, **k: None,
                                                  _draw_continue=lambda *a, **k: None), context)
        joined = " | ".join(texts)
        self.assertIn("No API key", joined)
        self.assertIn("No Anthropic Claude API key added", joined)


if __name__ == "__main__":
    unittest.main()
