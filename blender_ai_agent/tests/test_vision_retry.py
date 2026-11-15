"""The vision check was skipped when Gemini was slow or busy (log 20261114_150903:
'gemini-3.8-flash: timeout; gemini-3.5-flash-lite: 503'). One short wait and a second try now
happen before giving up, the review uses a shorter timeout so the fallback model gets its turn,
and quota errors are not retried."""

from . import _bpy_stub  # noqa: F401

import time
import unittest

from blender_ai_agent.agent import post_verify as pv
from blender_ai_agent.agent import self_correct as sc
from .test_auto_verify import THREE, Case, StubLLM, critique


class TestVisionRetry(Case):

    def make(self, llm, factory_cfgs=None):
        sleeps = []

        def factory(cfg):
            if factory_cfgs is not None:
                factory_cfgs.append(cfg)
            return llm

        verifier = pv.PostRunVerifier(self.caller, self.bridge, llm_factory=factory, config_loader=lambda: self.cfg,
                                      builder_config_loader=lambda: sc.BuilderConfig(api_key="k", request_timeout_s=120.0),
                                      sleep=sleeps.append)
        return verifier, sleeps

    def facts(self):
        return pv.RunFacts(created=THREE, types={n: "MESH" for n in THREE}, started=time.time())

    def test_busy_gemini_is_tried_again_and_the_review_happens(self):
        busy = sc.BuilderError("gemini-3.8-flash: timeout; gemini-3.5-flash-lite: 503",
                               "Gemini did not answer: gemini-3.8-flash: timeout; gemini-3.5-flash-lite: 503")
        llm = StubLLM(busy, critique(8))
        verifier, sleeps = self.make(llm)
        report = verifier.assess("make a car", self.facts())
        self.assertEqual(report.score, 8)
        self.assertEqual(report.vision_note, "")
        self.assertEqual(sleeps, [pv.PostRunVerifier.RETRY_WAIT_S])
        self.assertEqual(len(llm.calls), 2)

    def test_only_one_retry(self):
        busy = sc.BuilderError("x: 503", "Gemini did not answer: x: 503")
        verifier, sleeps = self.make(StubLLM(busy, busy))
        report = verifier.assess("make a car", self.facts())
        self.assertIn("vision check skipped", report.vision_note)
        self.assertEqual(len(sleeps), 1)

    def test_quota_is_not_retried(self):
        quota = sc.BuilderError("x: 429", "Gemini quota is used up (429). Try again in a little while.")
        verifier, sleeps = self.make(StubLLM(quota))
        report = verifier.assess("make a car", self.facts())
        self.assertIn("429", report.vision_note)
        self.assertEqual(sleeps, [])

    def test_review_uses_a_shorter_timeout(self):
        cfgs = []
        verifier, _ = self.make(StubLLM(critique(9)), factory_cfgs=cfgs)
        verifier.assess("make a car", self.facts())
        self.assertEqual(cfgs[0].request_timeout_s, pv.PostRunVerifier.VISION_TIMEOUT_S)


if __name__ == "__main__":
    unittest.main()


class TestUntilFixed(Case):

    def test_default_is_check_and_fix_until_it_passes(self):
        cfg = pv.VerifyConfig()
        self.assertTrue(cfg.until_fixed)
        self.assertGreaterEqual(cfg.max_rounds, 8)

    def test_keeps_fixing_past_two_rounds_until_it_passes(self):
        from .test_auto_verify import WorldAgent  # noqa: F401  (same fixtures as the controller tests)
        self.llm.answers = [critique(3, ["bad"]), critique(4, ["less bad"]), critique(5, ["better"]),
                            critique(6, ["almost"]), critique(8.5)]
        controller, agent = self.controller([{"create": THREE}, {}, {}, {}, {}], self.verifier(max_rounds=10))
        result = controller.submit("make a car")
        self.assertEqual(len(agent.received), 5)                                       # 1 + 4 fix rounds
        self.assertIn("fixed after 4 round(s)", result.reply_text)
        self.assertTrue(agent.received[4].startswith("AUTOMATIC CHECK (round 4)"))

    def test_safety_cap_is_reported(self):
        self.llm.answers = [critique(2, ["x"]), critique(3, ["x"]), critique(4, ["x"]), critique(5, ["x"])]
        controller, agent = self.controller([{"create": THREE}, {}, {}, {}], self.verifier(max_rounds=3))
        result = controller.submit("make a car")
        self.assertEqual(len(agent.received), 4)
        self.assertIn("safety limit of 3 rounds reached", result.reply_text)

    def test_used_up_quota_ends_the_loop(self):
        quota = sc.BuilderError("x: 429", "Gemini quota is used up (429). Try again in a little while.")
        self.llm.answers = [critique(3, ["x"]), quota]
        geometry_fix = [{"create": THREE}, {}, {}, {}]
        controller, agent = self.controller(geometry_fix, self.verifier(max_rounds=10))
        result = controller.submit("make a car")
        self.assertEqual(len(agent.received), 2)
        self.assertNotIn("round 2", " ".join(agent.received))

    def test_announce_has_no_fixed_limit(self):
        report = pv.CheckReport(score=3.0, needs_fix=True)
        self.assertIn("(round 5)", self.verifier().announce(report, 5))
