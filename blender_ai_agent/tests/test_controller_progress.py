from . import _bpy_stub  # noqa: F401

import unittest
from types import SimpleNamespace

from blender_ai_agent.copilot.controller import CopilotController
from blender_ai_agent.copilot.step_progress import ProgressHistory, ProgressTracker


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class FakeLogger:
    callback = None


class FakeAgent:
    """Har run() ek 'agent' step hai; `script` = {step_text_ko_pehchaanne_wala_shabd: action}."""

    def __init__(self, clock=None, seconds=10, script=None, with_logger=False):
        self.received = []
        self._clock = clock
        self._seconds = seconds
        self._script = script or {}
        self.controller = None
        self.seen_callbacks = []
        if with_logger:
            self._logger = FakeLogger()

    def run(self, user_input, state=None):
        self.received.append(user_input)
        if hasattr(self, "_logger"):
            self.seen_callbacks.append(self._logger.callback)
        if self._clock is not None:
            self._clock.advance(self._seconds)
        for word, action in self._script.items():
            if word in user_input:
                if action == "fail":
                    return SimpleNamespace(reply_text="could not build that", task_id="t", rolled_back=True)
                if action == "quota":
                    raise RuntimeError("429 You exceeded your current quota, limit: 20, model: gemini-3.6-flash")
                if action == "crash":
                    raise RuntimeError("something exploded")
                if action == "cancel":
                    self.controller.cancel()
        return SimpleNamespace(reply_text=f"ok: {user_input}", task_id="t", rolled_back=False)


class FakeSkill:
    name = "library_props"

    def __init__(self, clock=None, seconds=1):
        self.contexts = []
        self._clock = clock
        self._seconds = seconds

    def execute(self, context):
        self.contexts.append(context)
        if self._clock is not None:
            self._clock.advance(self._seconds)
        return SimpleNamespace(success=True, data={"model": "x"}, steps_completed=["a"], error=None)


class FakeSkillRegistry:
    def __init__(self, skill):
        self._skill = skill

    def find_best_match(self, text):
        return self._skill if any(w in text for w in ("campfire", "tent", "lantern")) else None


BIG = "make a campfire then add a tent then add a lantern then draw a fancy dragon"
PARTS = ["make a campfire", "add a tent", "add a lantern", "draw a fancy dragon"]


def build(script=None, seconds=10, with_logger=False, skill=False, **kwargs):
    clock = FakeClock()
    tracker = ProgressTracker(history=ProgressHistory(None), clock=clock)
    agent = FakeAgent(clock=clock, seconds=seconds, script=script, with_logger=with_logger)
    fake_skill = FakeSkill(clock=clock) if skill else None
    controller = CopilotController(
        agent, tracker=tracker,
        skill_registry=FakeSkillRegistry(fake_skill) if skill else None,
        tool_caller=object() if skill else None, **kwargs)
    agent.controller = controller
    return controller, agent, tracker, fake_skill, clock


class TestBigRequestsRunStepByStep(unittest.TestCase):

    def test_parts_run_one_by_one_in_order(self):
        controller, agent, tracker, _, _ = build()
        result = controller.submit(BIG)
        self.assertTrue(result.success, result.reply_text)
        self.assertEqual(agent.received, PARTS)                          # har step alag, ek-ek karke, sahi order mein
        snap = tracker.snapshot()
        self.assertEqual((snap.state, snap.total, snap.completed, snap.percent), ("done", 4, 4, 100.0))

    def test_summary_lists_every_step(self):
        controller, _, _, _, _ = build()
        result = controller.submit(BIG)
        lines = result.reply_text.splitlines()
        self.assertEqual(lines[0], "Done 4/4 steps in 0:40.")
        for number, part in enumerate(PARTS, 1):
            self.assertIn(f"✓ {number}. {part}", lines)

    def test_progress_is_reported_after_every_step(self):
        controller, _, _, _, _ = build()
        events = []
        controller.submit(BIG, on_progress=lambda text, data: events.append(text))
        joined = "\n".join(events)
        for marker in ("1/4", "2/4", "3/4", "4/4", "Done 4/4"):
            self.assertIn(marker, joined)
        percents = [int(e.split("%")[0].split("]")[-1]) for e in events if "[" in e and "%" in e]
        self.assertEqual(percents, sorted(percents))
        self.assertTrue(all(len(e) <= 45 for e in events), [e for e in events if len(e) > 45])

    def test_user_sees_the_plan_with_an_estimate_first(self):
        controller, _, _, _, _ = build()
        controller.submit(BIG)
        texts = [m.content for m in controller.session.get_messages()]
        self.assertTrue(any("4 steps" in t and "~1:20" in t for t in texts), texts)   # 4 x 20s default

    def test_user_message_is_recorded_once(self):
        controller, _, _, _, _ = build()
        controller.submit(BIG)
        user_messages = [m for m in controller.session.get_messages() if getattr(m.role, "value", m.role) == "user"]
        self.assertEqual(len(user_messages), 1)

    def test_numbered_list_and_new_lines(self):
        controller, agent, _, _, _ = build()
        controller.submit("1. make a floor\n2. add walls\n3. add a table")
        self.assertEqual(agent.received, ["make a floor", "add walls", "add a table"])

    def test_skill_steps_use_the_fast_path_and_are_cheap_in_the_estimate(self):
        controller, agent, tracker, skill, _ = build(skill=True)
        snapshots = []
        controller.submit(BIG, on_progress=lambda text, data: snapshots.append(tracker.snapshot().eta))
        self.assertEqual(agent.received, ["draw a fancy dragon"])        # sirf ye LLM tak gaya
        self.assertEqual([c["task"] for c in skill.contexts], ["make a campfire", "add a tent", "add a lantern"])
        self.assertEqual(snapshots[0], 3 + 3 + 3 + 20)                  # skill steps 3s, agent step 20s


class TestSmallRequestsAreUnchanged(unittest.TestCase):

    def test_two_parts_are_not_split(self):
        controller, agent, tracker, _, _ = build()
        text = "make a cube then add a sphere"
        result = controller.submit(text)
        self.assertTrue(result.success)
        self.assertEqual(agent.received, [text])
        self.assertEqual(result.reply_text, f"ok: {text}")               # koi summary nahi, jaisa pehle tha
        self.assertEqual(tracker.snapshot().total, 0)                     # single-task progress

    def test_on_progress_reaches_the_logger_untouched_and_no_extra_calls(self):
        controller, agent, _, _, _ = build(with_logger=True)
        calls = []

        def on_progress(event, data):
            calls.append(event)

        controller.submit("make a cube", on_progress=on_progress)
        self.assertEqual(agent.seen_callbacks, [on_progress])             # wahi function, koi wrapper nahi
        self.assertIsNone(agent._logger.callback)                         # baad mein hata diya
        self.assertEqual(calls, [])                                       # controller ne khud koi extra call nahi ki

    def test_auto_split_can_be_switched_off(self):
        controller, agent, _, _, _ = build(auto_split=False)
        controller.submit(BIG)
        self.assertEqual(agent.received, [BIG])

    def test_split_threshold_is_configurable(self):
        controller, agent, _, _, _ = build(split_min_parts=2)
        controller.submit("make a cube then add a sphere")
        self.assertEqual(agent.received, ["make a cube", "add a sphere"])

    def test_single_task_failure_and_exceptions_behave_as_before(self):
        controller, _, tracker, _, _ = build(script={"cube": "fail"})
        result = controller.submit("make a cube")
        self.assertFalse(result.success)
        self.assertEqual(result.reply_text, "could not build that")

        controller, _, tracker, _, _ = build(script={"cube": "crash"})
        with self.assertRaises(RuntimeError):
            controller.submit("make a cube")
        self.assertEqual(tracker.snapshot().state, "done")
        self.assertFalse(tracker.snapshot().ok)

    def test_cancelled_before_start(self):
        controller, agent, _, _, _ = build()
        controller.cancel()
        result = controller.submit(BIG)
        self.assertFalse(result.success)
        self.assertIsNone(result.reply_text)
        self.assertEqual(agent.received, [])


class TestFailuresDoNotLoseProgress(unittest.TestCase):

    def test_one_failed_step_does_not_stop_the_rest(self):
        controller, agent, tracker, _, _ = build(script={"tent": "fail"})
        result = controller.submit(BIG)
        self.assertEqual(agent.received, PARTS)                            # chaaron chale
        self.assertFalse(result.success)
        lines = result.reply_text.splitlines()
        self.assertEqual(lines[0], "Done 3/4 steps in 0:40.")
        self.assertIn("✓ 1. make a campfire", lines)
        self.assertTrue(any(l.startswith("✗ 2. add a tent — could not build that") for l in lines), lines)
        self.assertIn("✓ 4. draw a fancy dragon", lines)
        snap = tracker.snapshot()
        self.assertEqual((snap.completed, snap.failed), (3, 1))

    def test_a_crashing_step_is_contained(self):
        controller, agent, _, _, _ = build(script={"lantern": "crash"})
        result = controller.submit(BIG)
        self.assertEqual(agent.received, PARTS)
        self.assertFalse(result.success)
        self.assertIn("✗ 3. add a lantern", result.reply_text)
        self.assertIn("✓ 4. draw a fancy dragon", result.reply_text)

    def test_quota_stops_the_remaining_steps_instead_of_failing_each_one(self):
        controller, agent, tracker, _, _ = build(script={"tent": "quota"})
        result = controller.submit(BIG)
        self.assertEqual(agent.received, PARTS[:2])                        # step 2 par quota -> aage nahi
        self.assertFalse(result.success)
        lines = result.reply_text.splitlines()
        self.assertIn("✓ 1. make a campfire", lines)
        self.assertTrue(lines[2].startswith("✗ 2. add a tent — Gemini ka quota khatam"), lines[2])
        self.assertIn("- 3. add a lantern (skipped: quota khatam)", lines)
        self.assertIn("- 4. draw a fancy dragon (skipped: quota khatam)", lines)
        statuses = [s["status"] for s in tracker.snapshot().steps]
        self.assertEqual(statuses, ["done", "failed", "skipped", "skipped"])

    def test_cancel_between_steps_keeps_finished_work_and_skips_the_rest(self):
        controller, agent, tracker, _, _ = build(script={"tent": "cancel"})
        result = controller.submit(BIG)
        self.assertEqual(agent.received, PARTS[:2])
        self.assertIn("- 3. add a lantern (skipped: cancelled)", result.reply_text)
        self.assertEqual(tracker.snapshot().completed, 2)


if __name__ == "__main__":
    unittest.main()