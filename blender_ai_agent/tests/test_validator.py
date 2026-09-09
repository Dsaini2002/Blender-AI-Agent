from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability.validator import Validator, ValidationResult


class TestValidationResult(unittest.TestCase):

    def test_ok_result_is_valid(self):
        result = ValidationResult.ok()
        self.assertTrue(result.valid)
        self.assertEqual(result.reasons, [])

    def test_failed_result_carries_reasons(self):
        result = ValidationResult.failed("Object not found", "Wrong location")
        self.assertFalse(result.valid)
        self.assertEqual(result.reasons, ["Object not found", "Wrong location"])


class TestValidatorBase(unittest.TestCase):

    def test_cannot_instantiate_directly(self):
        with self.assertRaises(TypeError):
            Validator()

    def test_subclass_without_validate_fails(self):
        class BrokenValidator(Validator):
            pass

        with self.assertRaises(TypeError):
            BrokenValidator()

    def test_valid_subclass_works(self):
        class AlwaysValidValidator(Validator):
            def validate(self, expected, bridge):
                return ValidationResult.ok()

        validator = AlwaysValidValidator()
        result = validator.validate({}, bridge=None)
        self.assertTrue(result.valid)


if __name__ == "__main__":
    unittest.main()