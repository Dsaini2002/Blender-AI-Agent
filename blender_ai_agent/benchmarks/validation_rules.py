"""
ValidationRule — Step 8.7
=============================
Hinglish: Har rule ek specific cheez check karta hai — scene ko
source of truth maan kar (bridge se seedha padhta hai). Concrete
rules: ObjectExistsRule, ObjectTypeRule, TransformRule, MaterialRule,
ModifierRule — sab same `validate(bridge) -> ValidationResult`
interface follow karte hain (Polymorphism).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from .models import ValidationResult


class ValidationRule(ABC):
    rule_id: str = ""

    @abstractmethod
    def validate(self, bridge) -> ValidationResult:
        raise NotImplementedError


class ObjectExistsRule(ValidationRule):
    def __init__(self, object_name: str):
        self.rule_id = f"object_exists:{object_name}"
        self._object_name = object_name

    def validate(self, bridge) -> ValidationResult:
        obj = bridge.get_object(self._object_name)
        return ValidationResult(
            rule_id=self.rule_id,
            passed=obj is not None,
            expected=self._object_name,
            actual=obj.name if obj else None,
            message=f"Object '{self._object_name}' {'exists' if obj else 'not found'}.",
        )


class ObjectTypeRule(ValidationRule):
    def __init__(self, object_name: str, expected_type: str):
        self.rule_id = f"object_type:{object_name}"
        self._object_name = object_name
        self._expected_type = expected_type

    def validate(self, bridge) -> ValidationResult:
        obj = bridge.get_object(self._object_name)
        actual_type = obj.type if obj else None
        passed = obj is not None and actual_type == self._expected_type

        return ValidationResult(
            rule_id=self.rule_id,
            passed=passed,
            expected=self._expected_type,
            actual=actual_type,
            message=f"Expected type '{self._expected_type}', got '{actual_type}'.",
        )


class TransformRule(ValidationRule):
    """Hinglish: Location ka ek axis check karta hai — X/Y/Z, tolerance ke saath (floats exact match nahi hote)."""

    def __init__(self, object_name: str, axis: str, expected_value: float, tolerance: float = 0.01):
        axis_index = {"x": 0, "y": 1, "z": 2}[axis.lower()]
        self.rule_id = f"location_{axis.lower()}:{object_name}"
        self._object_name = object_name
        self._axis_index = axis_index
        self._expected_value = expected_value
        self._tolerance = tolerance

    def validate(self, bridge) -> ValidationResult:
        obj = bridge.get_object(self._object_name)
        if obj is None:
            return ValidationResult(
                rule_id=self.rule_id, passed=False,
                expected=self._expected_value, actual=None,
                message=f"Object '{self._object_name}' not found.",
            )

        actual_value = obj.location[self._axis_index]
        passed = abs(actual_value - self._expected_value) <= self._tolerance

        return ValidationResult(
            rule_id=self.rule_id,
            passed=passed,
            expected=self._expected_value,
            actual=actual_value,
            message=f"Expected {self._expected_value}, got {actual_value}.",
        )


class MaterialRule(ValidationRule):
    def __init__(self, object_name: str, expected_material: str):
        self.rule_id = f"material_assigned:{object_name}"
        self._object_name = object_name
        self._expected_material = expected_material

    def validate(self, bridge) -> ValidationResult:
        obj = bridge.get_object(self._object_name)
        actual_material = getattr(obj, "material_name", None) if obj else None
        passed = actual_material == self._expected_material

        return ValidationResult(
            rule_id=self.rule_id,
            passed=passed,
            expected=self._expected_material,
            actual=actual_material,
            message=f"Expected material '{self._expected_material}', got '{actual_material}'.",
        )


class ModifierRule(ValidationRule):
    def __init__(self, object_name: str, modifier_name: str, expected_type: str):
        self.rule_id = f"modifier:{object_name}:{modifier_name}"
        self._object_name = object_name
        self._modifier_name = modifier_name
        self._expected_type = expected_type

    def validate(self, bridge) -> ValidationResult:
        obj = bridge.get_object(self._object_name)
        modifier = obj.modifiers.get(self._modifier_name) if obj else None
        passed = modifier is not None and modifier.type == self._expected_type

        return ValidationResult(
            rule_id=self.rule_id,
            passed=passed,
            expected=self._expected_type,
            actual=modifier.type if modifier else None,
            message=f"Modifier '{self._modifier_name}' {'matches' if passed else 'does not match'}.",
        )