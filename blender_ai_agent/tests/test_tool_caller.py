from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.models import ToolCall
from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.tools.object_tools import CreateObjectTool, DeleteObjectTool
from blender_ai_agent.tools.registry import ToolRegistry
from .fakes import FakeBridge, FakeObject


def build_registry(objects=None):
    bridge = FakeBridge(objects=objects or [])
    registry = ToolRegistry()
    registry.register(CreateObjectTool(bridge))
    registry.register(DeleteObjectTool(bridge))
    return registry, bridge


class TestGetToolDefinitions(unittest.TestCase):

    def test_returns_definition_per_registered_tool(self):
        registry, _ = build_registry()
        caller = ToolCaller(registry)

        definitions = caller.get_tool_definitions()

        self.assertEqual(len(definitions), 2)
        names = {d.name for d in definitions}
        self.assertEqual(names, {"object.create", "object.delete"})

    def test_definition_has_description(self):
        registry, _ = build_registry()
        caller = ToolCaller(registry)

        definitions = caller.get_tool_definitions()
        create_def = next(d for d in definitions if d.name == "object.create")

        self.assertTrue(create_def.description)

    def test_definition_has_parameter_fields(self):
        registry, _ = build_registry()
        caller = ToolCaller(registry)

        definitions = caller.get_tool_definitions()
        create_def = next(d for d in definitions if d.name == "object.create")

        self.assertIn("name", create_def.parameters["fields"])


class TestToolCall(unittest.TestCase):

    def test_calls_correct_tool_successfully(self):
        registry, bridge = build_registry()
        caller = ToolCaller(registry)

        result = caller.call(ToolCall(tool_name="object.create", arguments={"name": "Cube"}))

        self.assertTrue(result.success)
        self.assertIsNotNone(bridge.get_object("Cube"))

    def test_unknown_tool_returns_failed_result_not_crash(self):
        registry, _ = build_registry()
        caller = ToolCaller(registry)

        result = caller.call(ToolCall(tool_name="does.not.exist", arguments={}))

        self.assertFalse(result.success)
        self.assertIn("Unknown tool", result.error)

    def test_call_with_invalid_arguments_fails_gracefully(self):
        registry, _ = build_registry()
        caller = ToolCaller(registry)

        result = caller.call(ToolCall(tool_name="object.create", arguments={}))  # 'name' missing

        self.assertFalse(result.success)

    def test_delete_tool_via_caller(self):
        cube = FakeObject(name="Cube")
        registry, bridge = build_registry(objects=[cube])
        caller = ToolCaller(registry)

        result = caller.call(ToolCall(tool_name="object.delete", arguments={"name": "Cube"}))

        self.assertTrue(result.success)
        self.assertIsNone(bridge.get_object("Cube"))


if __name__ == "__main__":
    unittest.main()