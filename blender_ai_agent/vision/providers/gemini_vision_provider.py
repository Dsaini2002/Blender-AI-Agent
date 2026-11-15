
import base64
import json

from .base import VisionProvider
from ..models import VisualObservation


class GeminiVisionProvider(VisionProvider):

    def __init__(self, api_key: str, model_name: str = "gemini-3.6-flash"):
        self._api_key = api_key
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._genai = genai
        except ImportError:                 # not in Blender's Python: use the REST client instead
            self._genai = None
        self._model_name = model_name

    def analyze(self, image, context):
        with open(image, "rb") as f:
            image_bytes = f.read()

        prompt = (
            "You are inspecting a Blender render for quality/correctness issues. "
            "Look for: floating objects (gaps where parts should touch), objects "
            "overlapping/clipping into each other, missing parts, wrong proportions, "
            "flat unbevelled edges where roundness was expected, or anything that "
            "looks visually wrong. Respond with ONLY raw JSON (no markdown fences), "
            'exactly this shape: {"description": "one sentence overview", '
            '"objects_detected": ["name1", "name2"], "issues": ["issue1", "issue2"], '
            '"confidence": 0.0-1.0}. If nothing looks wrong, "issues" should be an '
            "empty list and confidence should be high (close to 1.0)."
        )

        if self._genai is None:
            from ...agent import self_correct as sc
            client = sc.GeminiClient(sc.BuilderConfig(api_key=self._api_key, model=self._model_name))
            text = client.generate(prompt, [{"inline_data": {"mime_type": "image/png",
                                                             "data": base64.b64encode(image_bytes).decode("ascii")}}],
                                   json_mode=True, temperature=0.2, max_output_tokens=2048)
            return self._parse_response(text)

        model = self._genai.GenerativeModel(model_name=self._model_name)
        response = model.generate_content([
            prompt,
            {"mime_type": "image/png", "data": image_bytes},
        ])

        return self._parse_response(response.text)

    @staticmethod
    def _parse_response(text: str) -> VisualObservation:
        cleaned = (text or "").strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
            cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except (ValueError, TypeError):
            return VisualObservation(
                description=cleaned[:500] if cleaned else "No response from vision model.",
                confidence=0.3,
            )

        confidence = data.get("confidence", 0.5)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        return VisualObservation(
            description=data.get("description", ""),
            objects_detected=list(data.get("objects_detected", []) or []),
            issues=list(data.get("issues", []) or []),
            confidence=confidence,
        )