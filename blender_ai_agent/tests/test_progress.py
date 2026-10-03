import json
import os
import tempfile
import threading
import unittest

from blender_ai_agent.copilot.step_progress import (
    ProgressHistory, ProgressTracker, ascii_bar, format_duration,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def make(history=None):
    clock = FakeClock()
    return ProgressTracker(history=history or ProgressHistory(None), clock=clock), clock


class TestFormatting(unittest.TestCase):

    def test_duration(self):
        self.assertEqual(format_duration(0), "0:00")
        self.assertEqual(format_duration(35), "0:35")
        self.assertEqual(format_duration(125), "2:05")
        self.assertEqual(format_duration(3700), "1:01:40")
        self.assertEqual(format_duration(None), "--:--")
        self.assertEqual(format_duration(-5), "0:00")

    def test_bar(self):
        self.assertEqual(ascii_bar(0), "----------")
        self.assertEqual(ascii_bar(40), "####------")
        self.assertEqual(ascii_bar(100), "##########")
        self.assertEqual(ascii_bar(250), "##########")
        self.assertEqual(ascii_bar(-3), "----------")


class TestHistory(unittest.TestCase):

    def test_defaults_then_median_of_real_timings(self):
        history = ProgressHistory(None)
        self.assertEqual(history.estimate("agent"), 20.0)
        self.assertEqual(history.estimate("skill"), 3.0)
        for seconds in (10, 30, 12):
            history.record("agent", seconds)
        self.assertEqual(history.estimate("agent"), 12)                      # median, outliers se nahi hilta
        history.record("agent", 8)
        self.assertEqual(history.estimate("agent"), 11)                      # even count: beech ka average

    def test_nonsense_timings_are_ignored(self):
        history = ProgressHistory(None)
        for bad in (0, -1, 0.01, 99999):
            history.record("agent", bad)
        history.record("unknown-kind", 5)
        self.assertEqual(history.estimate("agent"), 20.0)

    def test_saved_and_reloaded_across_sessions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "history.json")
            first = ProgressHistory(path)
            first.record("skill", 2.0)
            first.record("skill", 4.0)
            second = ProgressHistory(path)
            self.assertEqual(second.estimate("skill"), 3.0)

    def test_corrupt_or_unwritable_history_never_breaks_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "history.json")
            with open(path, "w") as handle:
                handle.write("{not json")
            history = ProgressHistory(path)
            self.assertEqual(history.estimate("agent"), 20.0)
            with open(path, "w") as handle:
                json.dump({"agent": ["x", None, -5, 9999, 15.0]}, handle)
            self.assertEqual(ProgressHistory(path).estimate("agent"), 15.0)
        ProgressHistory(os.path.join(tempfile.gettempdir(), "no_such_dir_xyz", "\0bad", "h.json")).record("agent", 3)

    def test_history_is_capped(self):
        history = ProgressHistory(None)
        for i in range(1, 60):
            history.record("agent", float(i))
        self.assertLessEqual(len(history._data["agent"]), 20)


class TestSteppedProgress(unittest.TestCase):

    def run_step(self, tracker, clock, index, seconds, ok=True, kind=None):
        tracker.start_step(index, kind)
        clock.advance(seconds)
        tracker.finish_step(index, ok)

    def test_idle_by_default(self):
        tracker, _ = make()
        snap = tracker.snapshot()
        self.assertEqual(snap.state, "idle")
        self.assertEqual(tracker.status_line(), "")
        self.assertFalse(tracker.is_running())

    def test_plan_shows_total_and_an_initial_eta(self):
        tracker, _ = make()
        tracker.begin("big task", steps=["a", "b", "c", "d", "e"], kinds=["agent"] * 5)
        snap = tracker.snapshot()
        self.assertEqual((snap.state, snap.total, snap.index, snap.completed), ("running", 5, 1, 0))
        self.assertEqual(snap.eta, 100.0)                                    # 5 x 20s default
        self.assertEqual(snap.percent, 0.0)

    def test_percent_rises_monotonically_and_eta_falls(self):
        tracker, clock = make()
        tracker.begin("t", steps=list("abcde"), kinds=["agent"] * 5)
        percents, etas = [], []
        for index in range(5):
            tracker.start_step(index)
            for _ in range(4):
                clock.advance(5)
                snap = tracker.snapshot()
                percents.append(snap.percent)
                etas.append(snap.eta)
            tracker.finish_step(index, True)
            snap = tracker.snapshot()
            percents.append(snap.percent)
            etas.append(snap.eta)
        self.assertEqual(percents, sorted(percents))
        self.assertTrue(all(0 <= p <= 99 for p in percents[:-1]))            # beech mein kabhi 100 nahi
        self.assertEqual(percents[-1], 100.0)                                 # aakhri step khatam hote hi 100
        self.assertGreater(etas[0], etas[-1])
        tracker.finish(ok=True)
        done = tracker.snapshot()
        self.assertEqual((done.percent, done.eta, done.state, done.completed), (100.0, 0.0, "done", 5))

    def test_eta_adapts_when_steps_are_faster_than_expected(self):
        tracker, clock = make()
        tracker.begin("t", steps=list("abcde"), kinds=["agent"] * 5)       # expects 20s each
        self.run_step(tracker, clock, 0, 4)                                  # but took 4s
        self.run_step(tracker, clock, 1, 4)
        snap = tracker.snapshot()
        self.assertLess(snap.eta, 3 * 20.0 * 0.5)                           # 3 baaki: ~12s, 60s nahi
        self.assertGreaterEqual(snap.eta, 3 * 4.0 * 0.9)

    def test_eta_adapts_when_steps_are_slower_than_expected(self):
        tracker, clock = make()
        tracker.begin("t", steps=list("abcd"), kinds=["agent"] * 4)
        self.run_step(tracker, clock, 0, 60)
        self.assertGreater(tracker.snapshot().eta, 3 * 20.0)

    def test_skill_steps_are_cheap_in_the_estimate(self):
        tracker, _ = make()
        tracker.begin("t", steps=["a", "b", "c"], kinds=["skill", "skill", "agent"])
        self.assertEqual(tracker.snapshot().eta, 3 + 3 + 20)

    def test_long_running_step_does_not_hit_100_or_negative_eta(self):
        tracker, clock = make()
        tracker.begin("t", steps=["a", "b"], kinds=["agent", "agent"])
        tracker.start_step(0)
        clock.advance(500)
        snap = tracker.snapshot()
        self.assertLess(snap.percent, 100)
        self.assertGreater(snap.eta, 0)

    def test_failures_are_counted_and_still_advance_progress(self):
        tracker, clock = make()
        tracker.begin("t", steps=list("abc"), kinds=["agent"] * 3)
        self.run_step(tracker, clock, 0, 5)
        self.run_step(tracker, clock, 1, 5, ok=False)
        snap = tracker.snapshot()
        self.assertEqual((snap.completed, snap.failed), (1, 1))
        self.assertGreater(snap.percent, 50)
        self.run_step(tracker, clock, 2, 5)
        tracker.finish()
        self.assertFalse(tracker.snapshot().ok)                              # ek fail -> ok False
        self.assertIn("1 failed", tracker.status_line())

    def test_all_steps_finished_shows_100_before_the_summary(self):
        tracker, clock = make()
        tracker.begin("t", steps=["a", "b"], kinds=["agent", "agent"])
        self.run_step(tracker, clock, 0, 5)
        self.run_step(tracker, clock, 1, 5)
        snap = tracker.snapshot()                                            # tracker.finish() se pehle
        self.assertEqual((snap.state, snap.percent, snap.eta), ("running", 100.0, 0.0))

    def test_skip_remaining_marks_pending_and_running(self):
        tracker, clock = make()
        tracker.begin("t", steps=list("abcd"), kinds=["agent"] * 4)
        self.run_step(tracker, clock, 0, 5)
        tracker.start_step(1)
        tracker.skip_remaining("quota")
        statuses = [s["status"] for s in tracker.snapshot().steps]
        self.assertEqual(statuses, ["done", "skipped", "skipped", "skipped"])
        self.assertEqual(tracker.snapshot().steps[2]["note"], "quota")

    def test_timings_are_learned_for_next_time(self):
        history = ProgressHistory(None)
        tracker, clock = make(history)
        tracker.begin("t", steps=["a", "b"], kinds=["agent", "skill"])
        self.run_step(tracker, clock, 0, 8)
        self.run_step(tracker, clock, 1, 1)
        self.assertEqual(history.estimate("agent"), 8)
        self.assertEqual(history.estimate("skill"), 1)

    def test_status_line_is_short_and_informative(self):
        tracker, clock = make()
        tracker.begin("t", steps=list("abcde"), kinds=["agent"] * 5)
        self.run_step(tracker, clock, 0, 20)
        tracker.start_step(1)
        line = tracker.status_line()
        self.assertTrue(line.startswith("2/5 ["), line)
        self.assertIn("%", line)
        self.assertIn("left", line)
        self.assertLessEqual(len(line), 40)
        tracker.skip_remaining()
        tracker.finish(ok=True)
        self.assertEqual(tracker.status_line(), "Done 1/5 in 0:20")

    def test_snapshot_lists_steps_with_seconds(self):
        tracker, clock = make()
        tracker.begin("t", steps=["x", "y"], kinds=["agent", "agent"])
        self.run_step(tracker, clock, 0, 7)
        steps = tracker.snapshot().steps
        self.assertEqual((steps[0]["label"], steps[0]["status"], steps[0]["seconds"]), ("x", "done", 7))
        self.assertEqual((steps[1]["status"], steps[1]["seconds"]), ("pending", None))


class TestSingleTaskProgress(unittest.TestCase):

    def test_elapsed_and_typical_time(self):
        history = ProgressHistory(None)
        history.record("agent", 12)
        tracker, clock = make(history)
        tracker.begin("make a cube")
        clock.advance(7)
        snap = tracker.snapshot()
        self.assertEqual((snap.total, snap.state), (0, "running"))
        self.assertEqual(snap.elapsed, 7)
        self.assertEqual(snap.typical, 12)
        self.assertIsNone(snap.percent)
        self.assertEqual(tracker.status_line(), "Working 0:07  (usually ~0:12)")
        tracker.finish(ok=True)
        clock.advance(100)                                                   # finish ke baad elapsed freeze rehta hai
        self.assertEqual(tracker.snapshot().elapsed, 7)
        self.assertEqual(tracker.status_line(), "Done in 0:07")

    def test_events_are_counted(self):
        tracker, _ = make()
        tracker.begin("x")
        for event in ("model.request", "tool.start", "tool.done", "model.request", 123, None):
            tracker.note_event(event)
        snap = tracker.snapshot()
        self.assertEqual((snap.turns, snap.tool_events), (2, 2))

    def test_begin_resets_everything(self):
        tracker, clock = make()
        tracker.begin("a", steps=["x", "y"])
        tracker.begin("b")
        self.assertEqual(tracker.snapshot().total, 0)
        tracker.reset()
        self.assertEqual(tracker.snapshot().state, "idle")


class TestThreadSafety(unittest.TestCase):

    def test_parallel_updates_and_reads(self):
        tracker, clock = make()
        tracker.begin("t", steps=[f"s{i}" for i in range(20)], kinds=["skill"] * 20)
        errors = []

        def worker():
            try:
                for i in range(20):
                    tracker.start_step(i)
                    tracker.finish_step(i, True)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def reader():
            try:
                for _ in range(200):
                    tracker.snapshot()
                    tracker.status_line()
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=worker)] + [threading.Thread(target=reader) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()