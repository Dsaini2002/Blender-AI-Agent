from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.copilot.step_progress import ProgressHistory, ProgressTracker
from blender_ai_agent.ui import progress_panel


class FakeClock:
    def __init__(self):
        self.now = 500.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeLayout:
    """bpy ka layout nahi — bas jo draw hua use record karta hai."""

    def __init__(self):
        self.calls = []

    def label(self, text="", icon=None):
        self.calls.append(("label", text, icon))

    def progress(self, factor=0.0, type="BAR", text=""):
        self.calls.append(("progress", round(factor, 3), text))

    def box(self):
        return self

    def row(self):
        return self

    def texts(self):
        return [c[1] if c[0] == "label" else f"<bar {c[1]} {c[2]}>" for c in self.calls]


class FakeLayoutWithoutProgressBar(FakeLayout):
    """Purane Blender jaisa layout jisme layout.progress() hota hi nahi."""

    def __getattribute__(self, name):
        if name == "progress":
            raise AttributeError(name)
        return super().__getattribute__(name)


def make_panel(tracker, layout=None):
    progress_panel.get_tracker = lambda: tracker
    panel = progress_panel.AIAGENT_PT_progress()
    panel.layout = layout if layout is not None else FakeLayout()
    return panel


class TestProgressPanel(unittest.TestCase):

    def setUp(self):
        self.clock = FakeClock()
        self.tracker = ProgressTracker(history=ProgressHistory(None), clock=self.clock)
        self._original = progress_panel.get_tracker

    def tearDown(self):
        progress_panel.get_tracker = self._original

    def test_panel_is_a_child_of_the_copilot_panel_and_hidden_when_idle(self):
        self.assertEqual(progress_panel.AIAGENT_PT_progress.bl_parent_id, "AIAGENT_PT_panel")
        make_panel(self.tracker)
        self.assertFalse(progress_panel.AIAGENT_PT_progress.poll(None))
        self.tracker.begin("x")
        self.assertTrue(progress_panel.AIAGENT_PT_progress.poll(None))

    def test_stepwise_progress_is_drawn_with_bar_steps_and_eta(self):
        self.tracker.begin("big", steps=["make a floor", "add walls", "add a table"], kinds=["agent"] * 3)
        self.tracker.start_step(0)
        self.clock.advance(20)
        self.tracker.finish_step(0, True)
        self.tracker.start_step(1)
        self.clock.advance(5)
        panel = make_panel(self.tracker)
        panel.draw(None)
        texts = panel.layout.texts()

        self.assertTrue(texts[0].startswith("<bar"), texts)
        self.assertIn("Step 2/3: add walls", texts)
        self.assertTrue(any(t.startswith("Elapsed 0:25") and "left" in t for t in texts), texts)
        self.assertIn("1. make a floor", texts)
        self.assertIn("2. add walls", texts)
        self.assertIn("3. add a table", texts)
        icons = {c[1]: c[2] for c in panel.layout.calls if c[0] == "label" and c[1][:2] in ("1.", "2.", "3.")}
        self.assertEqual(icons, {"1. make a floor": "CHECKMARK", "2. add walls": "PLAY", "3. add a table": "DOT"})

    def test_ascii_fallback_when_layout_has_no_progress_bar(self):
        self.tracker.begin("big", steps=["a", "b"], kinds=["agent", "agent"])
        panel = make_panel(self.tracker, FakeLayoutWithoutProgressBar())
        panel.draw(None)
        self.assertTrue(panel.layout.texts()[0].startswith("[") and "%" in panel.layout.texts()[0])

    def test_finished_task_shows_the_result(self):
        self.tracker.begin("big", steps=["a", "b"], kinds=["agent", "agent"])
        for index, ok in ((0, True), (1, False)):
            self.tracker.start_step(index)
            self.clock.advance(10)
            self.tracker.finish_step(index, ok)
        self.tracker.finish()
        panel = make_panel(self.tracker)
        panel.draw(None)
        self.assertIn("Done 1/2  (1 failed) in 0:20", panel.layout.texts())
        icons = [c[2] for c in panel.layout.calls if c[0] == "label" and c[1].startswith(("1.", "2."))]
        self.assertEqual(icons, ["CHECKMARK", "ERROR"])

    def test_single_task_shows_elapsed_and_usual_time(self):
        self.tracker.begin("make a cube")
        self.clock.advance(7)
        panel = make_panel(self.tracker)
        panel.draw(None)
        texts = panel.layout.texts()
        self.assertIn("Working… 0:07", texts)
        self.assertIn("Usually takes ~0:20", texts)
        self.tracker.finish(ok=True)
        panel = make_panel(self.tracker)
        panel.draw(None)
        self.assertIn("Finished in 0:07", panel.layout.texts())

    def test_long_labels_are_clipped(self):
        long_label = "make a very very long request that would not fit the narrow sidebar at all"
        self.tracker.begin("x", steps=[long_label, "b"], kinds=["agent", "agent"])
        self.tracker.start_step(0)
        panel = make_panel(self.tracker)
        panel.draw(None)
        for text in panel.layout.texts():
            self.assertLessEqual(len(text), 50, text)

    def test_redraw_timer_tick_never_raises_and_keeps_running(self):
        self.assertEqual(progress_panel._redraw_tick(), 1.0)
        make_panel(self.tracker)
        self.tracker.begin("x")
        self.assertEqual(progress_panel._redraw_tick(), 1.0)       # bpy.context na ho tab bhi crash nahi


if __name__ == "__main__":
    unittest.main()