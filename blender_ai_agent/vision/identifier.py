"""
ObjectIdentifier — Step 5.6
================================
"""

from typing import List, Optional


class ObjectIdentifier:

    def __init__(self, bridge):
        self._bridge = bridge

    def identify(self, visual_description: str) -> Optional[str]:
        candidates = self._bridge.get_objects()
        description_words = set(self._normalize(visual_description).split())

        best_match = None
        best_score = 0

        for obj in candidates:
            obj_words = set(self._normalize(obj.name).split())
            score = len(description_words & obj_words)
            if score > best_score:
                best_score = score
                best_match = obj.name

        return best_match if best_score > 0 else None

    def identify_all(self, visual_descriptions: List[str]) -> dict:
        return {desc: self.identify(desc) for desc in visual_descriptions}

    @staticmethod
    def _normalize(text: str) -> str:
        """Hinglish: Underscores/special chars ko space banao, lowercase karo — 'Red_Cube' -> 'red cube'."""
        cleaned = "".join(ch if ch.isalnum() else " " for ch in text.lower())
        return cleaned