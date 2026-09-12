"""
Visual Similarity — Step 9.19
==================================
Hinglish: Do VisualObservations compare karke ek similarity score
deta hai. Spec khud kehta hai — "arbitrary similarity numbers claim
nahi karenge" — isliye scoring simple, transparent, aur explainable
rakha hai (object-overlap based), koi magic ML score nahi.
"""

from dataclasses import dataclass
from typing import List

from .models import VisualObservation


@dataclass
class SimilarityResult:
    score: float
    matching_objects: List[str]
    missing_objects: List[str]
    extra_objects: List[str]


class VisualSimilarityComparator:

    def compare(self, reference: VisualObservation, actual: VisualObservation) -> SimilarityResult:
        """
        Hinglish: Object-overlap based similarity — kitne reference
        ke objects actual mein bhi detect hue. Simple, explainable
        metric — future mein image-embedding based comparison isi
        interface ke peeche plug ho sakta hai.
        """
        ref_objects = set(reference.objects_detected)
        actual_objects = set(actual.objects_detected)

        matching = ref_objects & actual_objects
        missing = ref_objects - actual_objects
        extra = actual_objects - ref_objects

        score = len(matching) / len(ref_objects) if ref_objects else 0.0

        return SimilarityResult(
            score=score,
            matching_objects=sorted(matching),
            missing_objects=sorted(missing),
            extra_objects=sorted(extra),
        )