from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.reliability.errors import (
    ErrorCode,
    classify_tool_error,
    classify_validation_error,
)


class TestClassifyToolError(unittest.TestCase):

    def test_not_found_classified_as_object_not_found(self):
        error = classify_tool_error("Object 'Cube' not found in scene.")
        self.assertEqual(error.code, ErrorCode.OBJECT_NOT_FOUND)
        self.assertTrue(error.recoverable)

    def test_invalid_input_classified(self):
        error = classify_tool_error("Invalid input for tool 'object.create': missing name")
        self.assertEqual(error.code, ErrorCode.INVALID_INPUT)
        self.assertFalse(error.recoverable)

    def test_unknown_tool_classified(self):
        error = classify_tool_error("Unknown tool: 'foo.bar'")
        self.assertEqual(error.code, ErrorCode.TOOL_EXECUTION_FAILED)

    def test_unrecognized_message_classified_as_unknown(self):
        error = classify_tool_error("Something bizarre happened")
        self.assertEqual(error.code, ErrorCode.UNKNOWN_ERROR)


class TestClassifyValidationError(unittest.TestCase):

    def test_validation_failure_classified(self):
        error = classify_validation_error(["Expected location [3,0,0], got [0,0,0]."])
        self.assertEqual(error.code, ErrorCode.VALIDATION_FAILED)
        self.assertTrue(error.recoverable)


if __name__ == "__main__":
    unittest.main()