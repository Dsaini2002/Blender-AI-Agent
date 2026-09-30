"""
GeminiVisionProvider — REAL vision provider (pehle sirf Mock tha)
======================================================================
Hinglish: VisionObserveTool render leta hai, phir yahan image ko
Gemini ki multimodal API ko bhejte hain. Model ko strict JSON output
karne ko bolte hain (description, objects_detected, issues,
confidence) taaki VisualObservation mein reliably map ho sake.

Ye wahi "render -> dekho -> khud sudharo" loop enable karta hai jo
GPT-6 Astra ke Blender demo mein dikhaya gaya - hamara agent bhi ab
apna khud ka render "dekh" sakta hai, sirf coordinates ke hisaab se
guess nahi karta.
"""

import base64
import json

from .base import VisionProvider
from ..models import VisualObservation


class GeminiVisionProvider(VisionProvider):

    def __init__(self, api_key: str, model_name: str = "gemini-3.6-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
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
            # Hinglish: Model kabhi-kabhi JSON ke aas-paas extra text de deta hai -
            # raw text ko hi description bana kar, low-confidence observation
            # return karte hain, crash nahi karte.
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