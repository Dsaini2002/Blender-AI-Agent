"""
Concrete Tool Validators — Step 4.2
======================================
Hinglish: Validator (base class) ke concrete implementations. Har
ek check karta hai ki tool ne jo promise kiya, scene mein actually
wahi hua ya nahi — bridge se dobara padh kar (scene = source of truth).
"""

from typing import Any, Dict

from .validator import Validator, ValidationResult


class ObjectExistsValidator(Validator):
    """object.create ke baad: object sach mein exist karta hai aur type sahi hai?"""

    def validate(self, expected: Dict[str, Any], bridge) -> ValidationResult:
        name = expected.get("name")
        expected_type = expected.get("object_type", "MESH")

        obj = bridge.get_object(name)
        if obj is None:
            return ValidationResult.failed(f"Object '{name}' does not exist in scene.")

        if obj.type != expected_type:
            return ValidationResult.failed(
                f"Object '{name}' has type '{obj.type}', expected '{expected_type}'."
            )

        return ValidationResult.ok()


class ObjectDeletedValidator(Validator):
    """object.delete ke baad: object sach mein scene se gaya?"""

    def validate(self, expected: Dict[str, Any], bridge) -> ValidationResult:
        name = expected.get("name")

        obj = bridge.get_object(name)
        if obj is not None:
            return ValidationResult.failed(f"Object '{name}' still exists in scene.")

        return ValidationResult.ok()


class TransformValidator(Validator):
    """object.transform ke baad: location/rotation/scale actually update hui?"""

    def validate(self, expected: Dict[str, Any], bridge) -> ValidationResult:
        name = expected.get("name")
        obj = bridge.get_object(name)

        if obj is None:
            return ValidationResult.failed(f"Object '{name}' does not exist in scene.")

        reasons = []
        if expected.get("location") is not None:
            if list(obj.location) != list(expected["location"]):
                reasons.append(f"Expected location {expected['location']}, got {list(obj.location)}.")
        if expected.get("rotation") is not None:
            if list(obj.rotation_euler) != list(expected["rotation"]):
                reasons.append(f"Expected rotation {expected['rotation']}, got {list(obj.rotation_euler)}.")
        if expected.get("scale") is not None:
            if list(obj.scale) != list(expected["scale"]):
                reasons.append(f"Expected scale {expected['scale']}, got {list(obj.scale)}.")

        if reasons:
            return ValidationResult.failed(*reasons)

        return ValidationResult.ok()


class MaterialAssignedValidator(Validator):
    """material.assign ke baad: object pe sach mein wahi material laga hai?"""

    def validate(self, expected: Dict[str, Any], bridge) -> ValidationResult:
        object_name = expected.get("object_name")
        material_name = expected.get("material_name")

        obj = bridge.get_object(object_name)
        if obj is None:
            return ValidationResult.failed(f"Object '{object_name}' does not exist in scene.")

        actual_material = getattr(obj, "material_name", None)
        if actual_material != material_name:
            return ValidationResult.failed(
                f"Object '{object_name}' has material '{actual_material}', expected '{material_name}'."
            )

        return ValidationResult.ok()