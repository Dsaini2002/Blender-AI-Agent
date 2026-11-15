"""DatasetLoader"""

from typing import Any, Dict

from .models import BenchmarkTask, Difficulty


class DatasetLoader:

    def load_task(self, task_data: Dict[str, Any]) -> BenchmarkTask:
        difficulty_str = task_data.get("difficulty", "easy")

        return BenchmarkTask(
            id=task_data["id"],
            instruction=task_data["instruction"],
            expected_state=task_data.get("expected_state", {}),
            validation_rules=task_data.get("validation_rules", []),
            category=task_data.get("category", "basic"),
            difficulty=Difficulty(difficulty_str),
            timeout=task_data.get("timeout", 120),
        )

    def load_tasks(self, tasks_data: list) -> list:
        return [self.load_task(t) for t in tasks_data]