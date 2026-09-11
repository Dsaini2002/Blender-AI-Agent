"""
Evaluator — Step 8.8
========================
Hinglish: Task ke validation rules chalata hai, results collect karta
hai, aur score compute karta hai. Scene ko hamesha bridge se padhta
hai — agent ke "Done" statement pe kabhi trust nahi karta (Step 8.1).
"""

from typing import List

from .models import BenchmarkTask, TaskStatus, ValidationResult
from .validation_rules import ValidationRule


class Evaluator:

    def evaluate(self, task: BenchmarkTask, rules: List[ValidationRule], bridge) -> dict:
        """
        Hinglish: Har rule ko bridge (actual scene) ke against chalata
        hai. Return: {"status": TaskStatus, "score": float, "results": [...]}

        Score = (passed rules) / (total rules) — Step 8.10 partial scoring.
        """
        results: List[ValidationResult] = [rule.validate(bridge) for rule in rules]

        if not results:
            return {"status": TaskStatus.ERROR, "score": 0.0, "results": []}

        passed_count = sum(1 for r in results if r.passed)
        score = passed_count / len(results)
        status = TaskStatus.PASS if score == 1.0 else TaskStatus.FAIL

        return {"status": status, "score": score, "results": results}

    def evaluate_weighted(self, rules_with_weights: List[tuple], bridge) -> dict:
        """
        Hinglish: Step 8.11 — Weighted scoring. `rules_with_weights` =
        [(ValidationRule, weight), ...]. Total weight 100 hona zaroori
        nahi — hum proportion se calculate karte hain.
        """
        if not rules_with_weights:
            return {"status": TaskStatus.ERROR, "score": 0.0, "results": []}

        total_weight = sum(weight for _, weight in rules_with_weights)
        earned_weight = 0.0
        results = []

        for rule, weight in rules_with_weights:
            result = rule.validate(bridge)
            results.append(result)
            if result.passed:
                earned_weight += weight

        score = earned_weight / total_weight if total_weight > 0 else 0.0
        status = TaskStatus.PASS if score == 1.0 else TaskStatus.FAIL

        return {"status": status, "score": score, "results": results}