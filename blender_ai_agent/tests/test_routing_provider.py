from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import Message, ModelRequest, ModelResponse
from blender_ai_agent.routing.model_router import ModelTier, RoutingProvider, classify_complexity


class Recorder:
    def __init__(self, name, fail=False):
        self.name, self.fail, self.calls = name, fail, 0

    def generate(self, request):
        self.calls += 1
        if self.fail:
            raise RuntimeError("429 quota exceeded")
        return ModelResponse(content=self.name)


def request(*messages):
    return ModelRequest(messages=[Message(role=r, content=c) for r, c in messages] or [Message("user", "x")])


class TestComplexity(unittest.TestCase):

    def test_simple_and_complex_requests(self):
        self.assertEqual(classify_complexity("rename the cube to Box"), ModelTier.FAST)
        self.assertEqual(classify_complexity("make it red"), ModelTier.FAST)
        self.assertEqual(classify_complexity("make a red cube"), ModelTier.STRONG)        # building something new
        self.assertEqual(classify_complexity("Lighting: bright sunny day"), ModelTier.STRONG)
        self.assertEqual(classify_complexity("design a modern living room"), ModelTier.STRONG)
        self.assertEqual(classify_complexity("make 4 chairs"), ModelTier.STRONG)
        self.assertEqual(classify_complexity("make a table, a lamp, a sofa and a rug"), ModelTier.STRONG)


class TestRoutingProvider(unittest.TestCase):

    def setUp(self):
        self.fast, self.strong = Recorder("fast"), Recorder("strong")
        self.router = RoutingProvider(self.fast, self.strong)

    def test_simple_request_uses_fast_model(self):
        self.router.begin_task("make it red")
        self.assertEqual(self.router.generate(request(("user", "make it red"))).content, "fast")

    def test_complex_request_uses_strong_model(self):
        self.router.begin_task("design a kitchen with an island and stools")
        self.assertEqual(self.router.generate(request(("user", "x"))).content, "strong")

    def test_escalates_after_repeated_failures(self):
        self.router.begin_task("move the cube up")
        failing = request(("user", "move the cube up"), ("tool", "Tool 'object.create' failed: bad"),
                          ("tool", "Tool 'object.transform' failed: bad"))
        self.assertEqual(self.router.generate(failing).content, "strong")
        self.assertEqual(self.router.generate(request(("user", "x"))).content, "strong")   # stays strong
        self.assertEqual(self.router.escalations, 1)

    def test_fast_model_error_falls_back_to_strong(self):
        router = RoutingProvider(Recorder("fast", fail=True), self.strong)
        router.begin_task("rename the cube to Box")
        self.assertEqual(router.generate(request(("user", "rename the cube to Box"))).content, "strong")

    def test_automatic_check_always_uses_strong(self):
        self.assertEqual(self.router.begin_task("AUTOMATIC CHECK: the wheel floats"), ModelTier.STRONG)


class TestFastModelChoice(unittest.TestCase):

    def test_flash_is_never_routed_down_and_pro_routes_to_flash(self):
        from blender_ai_agent.routing.model_router import fast_model_for
        self.assertIsNone(fast_model_for("gemini", "gemini-3.6-flash"))
        self.assertEqual(fast_model_for("gemini", "gemini-3.1-pro-preview"), "gemini-3.6-flash")
        self.assertEqual(fast_model_for("openai", "gpt-6-astra"), "gpt-6-luna")     # cheap edits
        self.assertIsNone(fast_model_for("openai", "gpt-6-luna"))


if __name__ == "__main__":
    unittest.main()
