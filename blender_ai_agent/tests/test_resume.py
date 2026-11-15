"""15 Nov: 'beech mein cancel karke dusra provider choose kiya to wahi se continue hona chahiye' - a stopped / failed
run is remembered with its plan; Continue (with any provider) reuses the plan and builds only what is missing."""

from . import _bpy_stub  # noqa: F401

import unittest
from types import SimpleNamespace

from blender_ai_agent.agent.checklist import Item
from blender_ai_agent.agent.understand import Understanding
from blender_ai_agent.copilot import resume
from blender_ai_agent.copilot.controller import CopilotController


class ResumeTest(unittest.TestCase):

    def setUp(self):
        resume.clear()

    def tearDown(self):
        resume.clear()

    def plan(self):
        return Understanding(kind="new", checklist=[Item("table", 1, "table"), Item("book", 2, "book",
                                                                                     position="on the table")],
                             source="ai", tools=["object.create"])

    def test_stopped_run_is_continued_with_the_same_plan_and_another_provider(self):
        received = []

        class Agent:
            role_hint, tool_filter, _model_provider = "", None, None

            def run(self, message, state=None):
                received.append(message)
                if len(received) == 1:
                    controller._cancelled = True                         # the user pressed Stop
                    return SimpleNamespace(reply_text="Stopped by user.", task_id="t", rolled_back=False,
                                           stopped_reason="cancelled")
                return SimpleNamespace(reply_text="finished the rest", task_id="t", rolled_back=False,
                                       stopped_reason="stop")

        controller = CopilotController(Agent(), auto_split=False)
        controller.current_provider_name = "gemini"
        plan = self.plan()
        controller._understand = lambda text, progress=None: plan
        first = controller.submit("create a table with two books\n(Scene context: 1 object)")
        self.assertFalse(first.success)
        info = resume.pending()
        self.assertEqual(info["why"], "stopped by the user")
        self.assertEqual(info["request"], "create a table with two books")      # scene context left out

        # the user picks Claude and presses Continue: a new controller, the same plan, no new planning request
        controller = CopilotController(Agent(), auto_split=False)
        controller.current_provider_name = "claude"
        controller._understand = lambda *a, **k: self.fail("the plan must be reused, not asked again")
        text = resume.prompt()
        self.assertTrue(text.startswith(resume.MARK))
        self.assertIn("book", text)
        self.assertIn("Never build again what is already there", text)
        result = controller.submit(text)
        self.assertTrue(result.success, result.reply_text)
        self.assertIs(controller._understanding, plan)
        self.assertIn("Original request:\ncreate a table with two books", received[-1])
        self.assertIsNone(resume.pending())                                   # done: nothing left to continue

    def test_continuing_twice_keeps_the_original_request(self):
        resume.remember("create a table", self.plan(), "failed: quota")
        again = resume.prompt()
        resume.remember(again, self.plan(), "stopped by the user")
        self.assertEqual(resume.pending()["request"], "create a table")

    def test_a_question_is_not_remembered(self):
        controller = CopilotController(SimpleNamespace(), auto_split=False)
        controller._cancelled = False
        controller._understanding = Understanding(kind="question")
        controller._remember_unfinished("what is in my scene?", SimpleNamespace(success=False, status="failed"))
        self.assertIsNone(resume.pending())


if __name__ == "__main__":
    unittest.main()
