"""
Advanced benchmark tasks — Step 9.29
=========================================
Hinglish: Geometry Nodes aur Animation ke liye benchmark tasks —
Phase 8 ke pattern ko follow karte hue.
"""

from ..models import BenchmarkTask, Difficulty
from ..validation_rules import ValidationRule, ValidationResult


class GeometryNodesRule(ValidationRule):
    def __init__(self, object_name: str, node_group_name: str):
        self.rule_id = f"geometry_nodes:{object_name}"
        self._object_name = object_name
        self._node_group_name = node_group_name

    def validate(self, bridge) -> ValidationResult:
        modifier = bridge.get_geometry_nodes(self._object_name, self._node_group_name)
        return ValidationResult(
            rule_id=self.rule_id,
            passed=modifier is not None,
            expected=self._node_group_name,
            actual=modifier.name if modifier else None,
            message=f"Geometry Nodes modifier '{self._node_group_name}' {'found' if modifier else 'not found'}.",
        )


class KeyframeExistsRule(ValidationRule):
    def __init__(self, object_name: str, expected_frame: int):
        self.rule_id = f"keyframe:{object_name}:{expected_frame}"
        self._object_name = object_name
        self._expected_frame = expected_frame

    def validate(self, bridge) -> ValidationResult:
        frames = bridge.get_keyframes(self._object_name)
        passed = self._expected_frame in frames

        return ValidationResult(
            rule_id=self.rule_id,
            passed=passed,
            expected=self._expected_frame,
            actual=frames,
            message=f"Keyframe at frame {self._expected_frame} {'found' if passed else 'not found'}.",
        )


def create_geometry_nodes_task() -> BenchmarkTask:
    return BenchmarkTask(
        id="geometry_nodes_001",
        instruction="Add a geometry nodes setup named 'Scatter' to Hero.",
        category="geometry_nodes",
        difficulty=Difficulty.HARD,
    )


def create_geometry_nodes_rules(bridge) -> list:
    return [GeometryNodesRule("Hero", "Scatter")]


def create_bounce_animation_task() -> BenchmarkTask:
    return BenchmarkTask(
        id="animation_001",
        instruction="Make the ball bounce between frame 1 and frame 20.",
        category="animation",
        difficulty=Difficulty.MEDIUM,
    )


def create_bounce_animation_rules(bridge) -> list:
    return [
        KeyframeExistsRule("Ball", 1),
        KeyframeExistsRule("Ball", 20),
    ]