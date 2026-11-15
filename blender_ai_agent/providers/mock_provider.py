"""MockProvider"""

from .base import ModelProvider


class MockProvider(ModelProvider):

    def __init__(self, responses=None):
        self._responses = list(responses) if responses else []
        self._call_count = 0
        self.received_requests = []

    def generate(self, request):
        self.received_requests.append(request)

        if self._call_count >= len(self._responses):
            raise RuntimeError(
                f"MockProvider: no scripted response left for call #{self._call_count + 1}. "
                f"Only {len(self._responses)} response(s) were configured."
            )

        response = self._responses[self._call_count]
        self._call_count += 1
        return response

    @property
    def call_count(self) -> int:
        return self._call_count