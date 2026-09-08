from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import (
    Message,
    ModelRequest,
    ModelResponse,
    ToolCall,
    ToolDefinition,
    Usage,
)


class TestMessage(unittest.TestCase):

    def test_valid_message(self):
        msg = Message(role="user", content="Create a cube")
        self.assertEqual(msg.role, "user")

    def test_invalid_role_raises(self):
        with self.assertRaises(ValueError):
            Message(role="alien", content="hello")


class TestModelRequest(unittest.TestCase):

    def test_valid_request(self):
        req = ModelRequest(messages=[Message(role="user", content="hi")])
        self.assertEqual(len(req.messages), 1)
        self.assertEqual(req.temperature, 0.7)  # default

    def test_empty_messages_raises(self):
        with self.assertRaises(ValueError):
            ModelRequest(messages=[])

    def test_invalid_temperature_raises(self):
        with self.assertRaises(ValueError):
            ModelRequest(messages=[Message(role="user", content="hi")], temperature=5.0)

    def test_with_tools(self):
        tool_def = ToolDefinition(name="object.create", description="Creates an object")
        req = ModelRequest(messages=[Message(role="user", content="hi")], tools=[tool_def])
        self.assertEqual(req.tools[0].name, "object.create")


class TestModelResponse(unittest.TestCase):

    def test_text_response_has_no_tool_calls(self):
        resp = ModelResponse(content="Hello there!")
        self.assertFalse(resp.has_tool_calls)

    def test_tool_call_response(self):
        resp = ModelResponse(
            tool_calls=[ToolCall(tool_name="object.create", arguments={"name": "Cube"})],
            finish_reason="tool_calls",
        )
        self.assertTrue(resp.has_tool_calls)
        self.assertEqual(resp.tool_calls[0].tool_name, "object.create")

    def test_usage_total_tokens(self):
        usage = Usage(prompt_tokens=100, completion_tokens=50)
        self.assertEqual(usage.total_tokens, 150)

    def test_default_response_has_no_tool_calls(self):
        resp = ModelResponse()
        self.assertFalse(resp.has_tool_calls)


if __name__ == "__main__":
    unittest.main()