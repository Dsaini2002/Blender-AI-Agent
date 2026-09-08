"""
MockProvider — Step 3.1
==========================
Hinglish: Ye ek FAKE AI provider hai — koi real API call nahi karta,
koi internet ya API key ki zaroorat nahi.

Kyun zaroori hai?
- Agent/Planner ka poora logic test karna hai bina paisa kharch kiye
- Predictable responses chahiye tests ke liye (real LLM har baar
  thoda alag jawab de sakta hai — non-deterministic)
- Jaisa humne Blender ke bina `FakeBridge` banaya tha, waisa hi ye
  LLM ke bina `MockProvider` hai

Isse hum pehle se HI decide kar sakte hain — "jab ye specific
message aaye, ye specific response do" — taaki Agent ka behavior
predictably test ho sake.
"""

from .base import ModelProvider


class MockProvider(ModelProvider):
    """
    Hinglish: Constructor mein ek "script" diya jaata hai — responses
    ki list. Har `generate()` call pe list mein se agla response
    return hota hai, order mein.
    """

    def __init__(self, responses=None):
        self._responses = list(responses) if responses else []
        self._call_count = 0
        self.received_requests = []  # debugging/testing ke liye — kya bheja gaya tha

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