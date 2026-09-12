from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.vision.models import VisualObservation
from blender_ai_agent.vision.similarity import VisualSimilarityComparator


class TestVisualSimilarityComparator(unittest.TestCase):

    def test_identical_objects_gives_full_score(self):
        reference = VisualObservation(description="ref", objects_detected=["cube", "sphere"])
        actual = VisualObservation(description="actual", objects_detected=["cube", "sphere"])

        result = VisualSimilarityComparator().compare(reference, actual)

        self.assertEqual(result.score, 1.0)
        self.assertEqual(result.missing_objects, [])

    def test_partial_match(self):
        reference = VisualObservation(description="ref", objects_detected=["cube", "sphere"])
        actual = VisualObservation(description="actual", objects_detected=["cube"])

        result = VisualSimilarityComparator().compare(reference, actual)

        self.assertEqual(result.score, 0.5)
        self.assertEqual(result.missing_objects, ["sphere"])

    def test_extra_objects_detected(self):
        reference = VisualObservation(description="ref", objects_detected=["cube"])
        actual = VisualObservation(description="actual", objects_detected=["cube", "camera"])

        result = VisualSimilarityComparator().compare(reference, actual)

        self.assertEqual(result.extra_objects, ["camera"])

    def test_no_overlap_gives_zero_score(self):
        reference = VisualObservation(description="ref", objects_detected=["cube"])
        actual = VisualObservation(description="actual", objects_detected=["sphere"])

        result = VisualSimilarityComparator().compare(reference, actual)

        self.assertEqual(result.score, 0.0)

    def test_empty_reference_gives_zero_score(self):
        reference = VisualObservation(description="ref", objects_detected=[])
        actual = VisualObservation(description="actual", objects_detected=["cube"])

        result = VisualSimilarityComparator().compare(reference, actual)

        self.assertEqual(result.score, 0.0)


if __name__ == "__main__":
    unittest.main()