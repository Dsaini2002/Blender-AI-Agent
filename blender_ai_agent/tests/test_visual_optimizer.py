from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.optimization.visual_optimizer import VisualQualityOptimizer


class TestVisualQualityOptimizer(unittest.TestCase):

    def test_stops_when_target_reached_immediately(self):
        optimizer = VisualQualityOptimizer(
            render_fn=lambda: "image",
            score_fn=lambda obs: 0.95,
            improve_fn=lambda obs: None,
            target_score=0.9,
        )

        result = optimizer.optimize()

        self.assertEqual(result.stopped_reason, "target_reached")
        self.assertEqual(len(result.attempts), 1)

    def test_improves_over_iterations(self):
        scores = iter([0.5, 0.7, 0.95])

        optimizer = VisualQualityOptimizer(
            render_fn=lambda: "image",
            score_fn=lambda obs: next(scores),
            improve_fn=lambda obs: None,
            max_iterations=5,
            target_score=0.9,
        )

        result = optimizer.optimize()

        self.assertEqual(result.stopped_reason, "target_reached")
        self.assertEqual(len(result.attempts), 3)
        self.assertTrue(result.improved)

    def test_stops_at_max_iterations_if_target_never_reached(self):
        optimizer = VisualQualityOptimizer(
            render_fn=lambda: "image",
            score_fn=lambda obs: 0.5,  # kabhi target tak nahi pahunchta
            improve_fn=lambda obs: None,
            max_iterations=3,
            target_score=0.9,
        )

        result = optimizer.optimize()

        self.assertEqual(result.stopped_reason, "max_iterations_reached")
        self.assertEqual(len(result.attempts), 3)

    def test_improve_fn_not_called_on_final_iteration(self):
        """Hinglish: Agar last iteration hai, improve karne ka koi fayda nahi — render nahi hoga phir."""
        call_count = {"n": 0}

        def improve(obs):
            call_count["n"] += 1

        optimizer = VisualQualityOptimizer(
            render_fn=lambda: "image",
            score_fn=lambda obs: 0.5,
            improve_fn=improve,
            max_iterations=2,
            target_score=0.9,
        )

        optimizer.optimize()

        self.assertEqual(call_count["n"], 1)  # sirf iteration 1 ke baad, 2 (last) ke baad nahi


if __name__ == "__main__":
    unittest.main()