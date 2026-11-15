"""Multi-Agent benchmark tasks"""

from ..models import BenchmarkTask, Difficulty
from ..validation_rules import MaterialRule, ObjectExistsRule


def create_product_scene_task() -> BenchmarkTask:
    return BenchmarkTask(
        id="multi_agent_001",
        instruction="Create a cube named Hero and assign it a red material.",
        category="multi_agent",
        difficulty=Difficulty.MEDIUM,
    )


def create_product_scene_rules(bridge) -> list:
    return [
        ObjectExistsRule("Hero"),
        MaterialRule("Hero", "Red"),
    ]