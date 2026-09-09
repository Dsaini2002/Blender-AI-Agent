"""
MockVisionProvider — Step 5.1 / 5.18
========================================
Hinglish: Real vision API ke bina test karne ke liye — jaisa
MockProvider (Phase 3) LLM ke bina test karne dete tha.

Same "scripted responses" pattern — predictable, deterministic.
"""

from .base import VisionProvider


class MockVisionProvider(VisionProvider):

    def __init__(self, observations=None):
        self._observations = list(observations) if observations else []
        self._call_count = 0
        self.received_calls = []  # (image, context) pairs — testing/debugging ke liye

    def analyze(self, image, context):
        self.received_calls.append((image, context))

        if self._call_count >= len(self._observations):
            raise RuntimeError(
                f"MockVisionProvider: no scripted observation left for call #{self._call_count + 1}."
            )

        observation = self._observations[self._call_count]
        self._call_count += 1
        return observation

    @property
    def call_count(self) -> int:
        return self._call_count