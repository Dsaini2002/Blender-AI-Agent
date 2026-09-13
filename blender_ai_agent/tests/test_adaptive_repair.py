from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.adaptive_repair import AdaptiveRepairPlanner, RepairCandidate


class TestAdaptiveRepairPlanner(unittest.TestCase):

    def test_generates_candidates_from_multiple_generators(self):
        def generator_a(error):
            return [RepairCandidate(name="retry", confidence=0.5, action=lambda: None)]

        def generator_b(error):
            return [RepairCandidate(name="re-inspect", confidence=0.8, action=lambda: None)]

        planner = AdaptiveRepairPlanner(candidate_generators=[generator_a, generator_b])
        candidates = planner.generate_candidates("some_error")

        self.assertEqual(len(candidates), 2)

    def test_select_repair_picks_highest_confidence(self):
        def generator(error):
            return [
                RepairCandidate(name="re-find object", confidence=0.6, action=lambda: "a"),
                RepairCandidate(name="re-create material", confidence=0.9, action=lambda: "b"),
                RepairCandidate(name="re-link material", confidence=0.4, action=lambda: "c"),
            ]

        planner = AdaptiveRepairPlanner(candidate_generators=[generator])
        best = planner.select_repair("material_assignment_failed")

        self.assertEqual(best.name, "re-create material")

    def test_no_candidates_raises(self):
        planner = AdaptiveRepairPlanner(candidate_generators=[])

        with self.assertRaises(ValueError):
            planner.select_repair("error")

    def test_rank_candidates_orders_best_first(self):
        def generator(error):
            return [
                RepairCandidate(name="low", confidence=0.2, action=lambda: None),
                RepairCandidate(name="high", confidence=0.9, action=lambda: None),
            ]

        planner = AdaptiveRepairPlanner(candidate_generators=[generator])
        ranked = planner.rank_candidates("error")

        self.assertEqual(ranked[0].name, "high")
        self.assertEqual(ranked[1].name, "low")


if __name__ == "__main__":
    unittest.main()