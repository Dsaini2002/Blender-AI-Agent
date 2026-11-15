"""Basic benchmark tasks"""

from ..models import BenchmarkTask, Difficulty
from ..validation_rules import ObjectExistsRule, ObjectTypeRule


def create_cube_task() -> BenchmarkTask:
    return BenchmarkTask(
        id="object_create_001",
        instruction="Create a cube named Hero.",
        expected_state={"objects": [{"name": "Hero", "type": "MESH"}]},
        validation_rules=["object_exists", "object_type"],
        category="basic",
        difficulty=Difficulty.EASY,
    )


def create_cube_rules(bridge) -> list:
    return [
        ObjectExistsRule("Hero"),
        ObjectTypeRule("Hero", "MESH"),
    ]