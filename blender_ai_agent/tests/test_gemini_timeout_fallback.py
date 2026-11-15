from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.self_correct import BuilderConfig, BuilderError, GeminiClient


class SlowPrimary(GeminiClient):
    def __init__(self, cfg, slow=("main",)):
        super().__init__(cfg)
        self.slow, self.asked = set(slow), []

    def _request(self, url, payload=None):
        model = url.split("/models/")[1].split(":")[0]
        self.asked.append(model)
        if model in self.slow:
            raise BuilderError("timeout", "Gemini did not answer within 1s.")
        return 200, {"candidates": [{"content": {"parts": [{"text": f"ok from {model}"}]}}]}


class TestTimeoutFallsBackToTheOtherModel(unittest.TestCase):

    def cfg(self):
        cfg = BuilderConfig()
        cfg.api_key, cfg.model, cfg.fallback_model = "k", "main", "lite"
        return cfg

    def test_slow_model_is_skipped(self):
        client = SlowPrimary(self.cfg())
        self.assertEqual(client.generate("sys", [{"text": "hi"}]), "ok from lite")
        self.assertEqual(client.asked, ["main", "lite"])

    def test_all_models_slow_gives_a_clear_error(self):
        client = SlowPrimary(self.cfg(), slow=("main", "lite"))
        with self.assertRaises(BuilderError) as caught:
            client.generate("sys", [{"text": "hi"}])
        self.assertIn("did not answer", caught.exception.user_message)


if __name__ == "__main__":
    unittest.main()
