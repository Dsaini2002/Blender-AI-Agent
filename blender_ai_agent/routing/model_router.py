"""ModelRouter"""

from enum import Enum


class ModelTier(str, Enum):
    FAST = "fast"        # simple, deterministic-ish tasks
    STRONG = "strong"     # complex planning/reasoning
    VISION = "vision"     # visual ambiguity involved


class ModelRouter:

    def __init__(self, providers: dict):
        self._providers = providers

    def route(self, instruction: str, requires_vision: bool = False, subtask_count: int = 1) -> ModelTier:
        if requires_vision:
            return ModelTier.VISION
        if subtask_count > 1:
            return ModelTier.STRONG
        return ModelTier.FAST

    def get_provider(self, tier: ModelTier):
        if tier.value not in self._providers:
            raise KeyError(f"No provider registered for tier '{tier.value}'.")
        return self._providers[tier.value]

    def route_and_get(self, instruction: str, requires_vision: bool = False, subtask_count: int = 1):
        tier = self.route(instruction, requires_vision, subtask_count)
        return self.get_provider(tier)

# =============================================================================
# Live routing: fast model for simple requests, strong model for complex ones
# =============================================================================
import re as _re

FAST_MODELS = {
    # chosen (strong) model -> lighter model for trivial edits. Flash-Lite / 20B are too weak for building scenes,
    # so a Flash model is never routed down; a Pro model routes trivial edits to Flash.
    "gemini": {"pro": "gemini-3.6-flash"},
    "claude": {"claude-opus-5-5": "claude-sonnet-5-5"},
    # OpenAI: trivial edits ('make the sofa red') go to the cheap Luna, everything else uses the picked model
    "openai": {"gpt-6-astra": "gpt-6-luna", "gpt-6-astra-pro": "gpt-6-luna", "gpt-6-sol": "gpt-6-luna"},
}


def fast_model_for(provider: str, chosen_model: str):
    table = FAST_MODELS.get(provider) or {}
    chosen = (chosen_model or "").lower()
    for key, fast in table.items():
        if key == chosen or (key == "pro" and "pro" in chosen):
            return fast if fast != chosen_model else None
    return None

_COMPLEX_WORDS = _re.compile(
    r"\b(design|scene|room|interior|house|building|city|town|street|campus|college|school|office|landscape|"
    r"environment|realistic|detailed|detail|complex|whole|entire|full|several|multiple|many|improve|refine|fix|"
    r"redo|better|vehicle|car|robot|animal|character|furniture|kitchen|bedroom|living|garden|park|village|castle)\b",
    _re.IGNORECASE)
_COUNT_WORDS = _re.compile(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\b", _re.IGNORECASE)


_TRIVIAL = _re.compile(
    r"^\s*(?:please\s+)?(?:rename|move|delete|remove|hide|show|rotate|turn|scale|resize|make it|make the|colou?r|paint|"
    r"set|change|select|duplicate|copy|undo|bevel|smooth|shade)\b", _re.IGNORECASE)


def classify_complexity(text: str) -> ModelTier:
    """FAST only for a short edit of something that already exists ("rename the cube to Box", "make it red").
    Building anything new, and every longer request, goes to the chosen (strong) model."""
    text = (text or "").strip()
    if not text or "\n" in text or len(text.split()) > 10:
        return ModelTier.STRONG
    if _COMPLEX_WORDS.search(text) or _COUNT_WORDS.search(text):
        return ModelTier.STRONG
    if len(_re.findall(r",|\band\b|\bthen\b|\bwith\b", text, _re.IGNORECASE)) >= 2:
        return ModelTier.STRONG
    return ModelTier.FAST if _TRIVIAL.search(text) else ModelTier.STRONG


class RoutingProvider:
    """A ModelProvider that holds a fast and a strong provider of the same service.

    - begin_task(text) picks the tier for the request (classify_complexity).
    - On a FAST request it escalates to STRONG for the rest of the request once two tool calls have failed, the
      automatic check asks for fixes, or the fast model raises (quota, rate limit, outage).
    """

    ESCALATE_AFTER_FAILURES = 2

    def __init__(self, fast, strong, fast_name: str = "", strong_name: str = ""):
        self._fast = fast
        self._strong = strong
        self.fast_name = fast_name
        self.strong_name = strong_name
        self.tier = ModelTier.STRONG
        self.last_tier = None
        self.escalations = 0

    def begin_task(self, text: str) -> ModelTier:
        self.tier = classify_complexity(text)
        if (text or "").startswith("AUTOMATIC CHECK"):
            self.tier = ModelTier.STRONG
        return self.tier

    def generate(self, request):
        if self.tier == ModelTier.FAST and self._should_escalate(request):
            self.tier = ModelTier.STRONG
            self.escalations += 1
        if self.tier == ModelTier.FAST:
            try:
                self.last_tier = ModelTier.FAST
                return self._fast.generate(request)
            except Exception:  # noqa: BLE001 — quota / outage on the light model: the strong one takes over
                self.tier = ModelTier.STRONG
                self.escalations += 1
        self.last_tier = ModelTier.STRONG
        return self._strong.generate(request)

    def _should_escalate(self, request) -> bool:
        failures = 0
        for message in getattr(request, "messages", []) or []:
            content = getattr(message, "content", "") or ""
            if message.role == "tool" and "' failed:" in content and "Not run:" not in content:
                failures += 1
            if message.role == "user" and ("vision.observe reported" in content or content.startswith("AUTOMATIC CHECK")):
                return True
        return failures >= self.ESCALATE_AFTER_FAILURES
