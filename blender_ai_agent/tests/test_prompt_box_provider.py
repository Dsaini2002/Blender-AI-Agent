"""15 Nov: the prompt box grows with the text and scrolls after 12 lines, only a Paste button; picking Groq in the
panel's top row did nothing when its key had arrived after start-up ('Provider not found in registry')."""

from . import _bpy_stub  # noqa: F401

import unittest
from types import SimpleNamespace
from unittest import mock

from blender_ai_agent.ui import panel


class FakeLines(list):
    def add(self):
        item = SimpleNamespace(text="")
        self.append(item)
        return item


def scene(text=""):
    return SimpleNamespace(aiagent_copilot_input=text, aiagent_prompt_lines=FakeLines(), aiagent_prompt_line_index=0)


class PromptBoxTest(unittest.TestCase):

    def test_box_lines_follow_the_prompt(self):
        s = scene()
        panel.set_prompt(s, "line one\n\nline three " + "word " * 30)
        texts = [item.text for item in s.aiagent_prompt_lines]
        self.assertEqual(texts[0], "line one")
        self.assertEqual(texts[1], "")
        self.assertGreater(len(texts), 3)                      # the long line is wrapped
        self.assertEqual(s.aiagent_prompt_line_index, -1)      # no highlighted row
        panel.set_prompt(s, "")
        self.assertEqual(len(s.aiagent_prompt_lines), 0)

    def test_box_grows_then_scrolls(self):
        calls = []
        layout = mock.MagicMock()
        layout.box.return_value = layout
        layout.column.return_value = layout
        layout.row.return_value = layout
        layout.template_list.side_effect = lambda *a, **k: calls.append(k)
        for count, rows in ((3, 3), (40, panel.PROMPT_BOX_ROWS)):
            s = scene()
            panel.set_prompt(s, "\n".join(f"line {i}" for i in range(count)))
            calls.clear()
            panel._draw_prompt_box(layout, s, panel._BOX["width"] + 6)
            self.assertEqual(calls[0]["rows"], rows)
            self.assertEqual(calls[0]["maxrows"], panel.PROMPT_BOX_ROWS)

    def test_only_the_paste_button(self):
        layout = mock.MagicMock()
        layout.box.return_value = layout
        layout.column.return_value = layout
        layout.row.return_value = layout
        panel._draw_prompt_box(layout, scene("hello"), 40)
        ops = [c.args[0] for c in layout.operator.call_args_list]
        self.assertEqual(ops, ["aiagent.prompt_paste"])

    def test_ctrl_v_in_the_field_fills_the_box_with_every_line(self):
        s = scene("first line")
        context = SimpleNamespace(window_manager=SimpleNamespace(clipboard="first line\nsecond line\nthird line"))
        panel.on_prompt_changed(s, context)
        self.assertEqual(s.aiagent_copilot_input, "first line\nsecond line\nthird line")
        self.assertEqual([i.text for i in s.aiagent_prompt_lines], ["first line", "second line", "third line"])


class ProviderSwitchTest(unittest.TestCase):

    def test_key_that_came_later_rebuilds_the_providers(self):
        import blender_ai_agent as addon
        registry = mock.MagicMock()
        registry.list_providers.return_value = ["mock", "gemini"]
        s = SimpleNamespace(aiagent_provider_choice="openai", aiagent_openai_model_choice="gpt-6-astra",
                            aiagent_is_running=False)
        with mock.patch.object(panel, "_has_key", return_value=True), \
                mock.patch.object(addon, "get_provider_registry", return_value=registry), \
                mock.patch.object(addon, "refresh_provider_registry") as refresh, \
                mock.patch.object(addon, "get_copilot_controller") as get:
            panel.on_provider_changed(None, SimpleNamespace(scene=s))
        refresh.assert_called_once()
        get.assert_called_with(provider_name="openai", model_name="gpt-6-astra")
        self.assertIn("Connected to OpenAI", panel.SWITCH_NOTE["text"])
        self.assertFalse(panel.SWITCH_NOTE["error"])

    def test_no_key_or_busy_is_said_in_the_panel(self):
        s = SimpleNamespace(aiagent_provider_choice="claude", aiagent_is_running=False)
        with mock.patch.object(panel, "_has_key", return_value=False):
            panel.on_provider_changed(None, SimpleNamespace(scene=s))
        self.assertTrue(panel.SWITCH_NOTE["error"])
        self.assertIn("no API key", panel.SWITCH_NOTE["text"])
        panel.on_provider_changed(None, SimpleNamespace(scene=SimpleNamespace(aiagent_is_running=True)))
        self.assertIn("after this run", panel.SWITCH_NOTE["text"])
        panel.SWITCH_NOTE.update(text="", error=False)


class PanelChoiceWinsTest(unittest.TestCase):

    def test_generate_goes_back_to_the_provider_in_the_panel(self):
        controller = SimpleNamespace(current_provider_name="claude", current_model_name="claude-sonnet-5-5")
        fresh = SimpleNamespace(current_provider_name="gemini", current_model_name="gemini-3.6-flash")
        s = SimpleNamespace(aiagent_provider_choice="gemini", aiagent_model_choice="gemini-3.6-flash")
        with mock.patch.object(panel, "_has_key", return_value=True), \
                mock.patch.object(panel, "_apply_provider", return_value="Connected to Google Gemini") as apply, \
                mock.patch.object(panel, "_controller_or_none", return_value=fresh):
            self.assertIs(panel.use_panel_choice(s, controller), fresh)
            apply.assert_called_once()
            apply.reset_mock()
            self.assertIs(panel.use_panel_choice(s, fresh), fresh)       # already right: nothing rebuilt
            apply.assert_not_called()
        panel.SWITCH_NOTE.update(text="", error=False)

    def test_no_key_for_the_panel_choice_keeps_the_working_one(self):
        controller = SimpleNamespace(current_provider_name="gemini", current_model_name=None)
        s = SimpleNamespace(aiagent_provider_choice="claude")
        with mock.patch.object(panel, "_has_key", return_value=False):
            self.assertIs(panel.use_panel_choice(s, controller), controller)


class KeyAskedOnceTest(unittest.TestCase):

    def test_key_survives_removing_and_installing_the_addon(self):
        import os
        from blender_ai_agent import prefs
        os.environ.pop("OPENAI_API_KEY", None)
        prefs.remember_key("OPENAI_API_KEY", "sk-once")
        self.assertEqual(oct(os.stat(prefs.keys_file()).st_mode)[-3:], "600")
        prefs.load_remembered_keys()                      # what a new install does
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "sk-once")
        os.environ["OPENAI_API_KEY"] = "sk-from-env"
        prefs.load_remembered_keys()                      # never over a key that is set
        self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-from-env")
        prefs.remember_key("OPENAI_API_KEY", "")
        self.assertNotIn("OPENAI_API_KEY", prefs._read_key_file())
        os.environ.pop("OPENAI_API_KEY", None)


if __name__ == "__main__":
    unittest.main()
