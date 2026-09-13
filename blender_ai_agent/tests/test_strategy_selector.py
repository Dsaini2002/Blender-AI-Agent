from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.strategy import Strategy, StrategySelector


class TestStrategy(unittest.TestCase):

    def test_score_computed_correctly(self):
        strategy = Strategy(name="bevel", reliability=0.9, expected_quality=0.8, execution_cost=0.2)
        self.assertAlmostEqual(strategy.score, 1.5)

    def test_invalid_reliability_raises(self):
        with self.assertRaises(ValueError):
            Strategy(name="x", reliability=1.5, expected_quality=0.5, execution_cost=0.1)


class TestStrategySelector(unittest.TestCase):

    def test_selects_highest_score(self):
        strategies = [
            Strategy(name="mesh_modeling", reliability=0.7, expected_quality=0.9, execution_cost=0.5),
            Strategy(name="bevel_modifier", reliability=0.95, expected_quality=0.7, execution_cost=0.1),
            Strategy(name="geometry_nodes", reliability=0.6, expected_quality=0.95, execution_cost=0.6),
        ]

        best = StrategySelector().select_best(strategies)

        self.assertEqual(best.name, "bevel_modifier")  # highest score: 0.95+0.7-0.1=1.55

    def test_empty_strategies_raises(self):
        with self.assertRaises(ValueError):
            StrategySelector().select_best([])

    def test_rank_orders_best_to_worst(self):
        strategies = [
            Strategy(name="low", reliability=0.3, expected_quality=0.3, execution_cost=0.3),
            Strategy(name="high", reliability=0.9, expected_quality=0.9, execution_cost=0.1),
        ]

        ranked = StrategySelector().rank(strategies)

        self.assertEqual(ranked[0].name, "high")
        self.assertEqual(ranked[1].name, "low")


if __name__ == "__main__":
    unittest.main()