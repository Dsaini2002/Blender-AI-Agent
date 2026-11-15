from . import _bpy_stub  # noqa: F401

import typing
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from blender_ai_agent.agent.tool_caller import ToolCaller
from blender_ai_agent.input_coercion import coerce_value
from blender_ai_agent.providers.base import portable_schema
from blender_ai_agent.tools.base import Tool, ToolResult


@dataclass
class _Input:
    name: str
    points: Optional[List[List[float]]] = None
    faces: List[List[int]] = field(default_factory=list)
    names: Optional[List[str]] = None
    properties: Dict[str, Any] = field(default_factory=dict)
    ops: List[Dict[str, Any]] = field(default_factory=list)
    anything: Any = None
    flag: bool = False
    count: int = 1


class _Tool(Tool):
    name = "demo.tool"
    description = "demo"
    input_model = _Input

    def run(self, validated_input):
        return ToolResult.ok({"input": validated_input})


class _Registry:
    def __init__(self, tool):
        self._tool = tool

    def list_tools(self):
        return [self._tool.name]

    def get(self, name):
        return self._tool


class TestToolSchema(unittest.TestCase):

    def setUp(self):
        self.schema = ToolCaller(_Registry(_Tool())).get_tool_definitions()[0].parameters
        self.props = self.schema["properties"]

    def test_nested_lists_keep_their_element_types(self):
        self.assertEqual(self.props["points"], {"type": "array", "items": {"type": "array", "items": {"type": "number"}}})
        self.assertEqual(self.props["faces"]["items"]["items"], {"type": "integer"})
        self.assertEqual(self.props["names"], {"type": "array", "items": {"type": "string"}})

    def test_dicts_are_objects_and_scalars_are_typed(self):
        self.assertEqual(self.props["properties"], {"type": "object"})
        self.assertEqual(self.props["flag"], {"type": "boolean"})
        self.assertEqual(self.props["count"], {"type": "integer"})
        self.assertEqual(self.schema["required"], ["name"])

    def test_portable_schema_gives_every_node_a_type(self):
        portable = portable_schema(self.schema, top=True)
        self.assertEqual(portable["properties"]["properties"]["type"], "string")
        self.assertEqual(portable["properties"]["ops"]["items"]["type"], "string")
        self.assertEqual(portable["properties"]["anything"]["type"], "string")
        self.assertEqual(portable["properties"]["points"]["items"]["items"], {"type": "number"})

    def test_json_strings_are_parsed_back(self):
        self.assertEqual(coerce_value('[[0, 0, 0], [1, 2, 3]]', Optional[List[List[float]]]), [[0, 0, 0], [1, 2, 3]])
        self.assertEqual(coerce_value('{"width": 0.02}', Dict[str, Any]), {"width": 0.02})
        self.assertEqual(coerce_value(['{"op": "melt"}'], List[Dict[str, Any]]), [{"op": "melt"}])
        self.assertEqual(coerce_value('[1, 2]', typing.Any), [1, 2])
        self.assertEqual(coerce_value("plain text", typing.Any), "plain text")

    def test_tool_accepts_json_string_arguments(self):
        result = _Tool().execute({"name": "x", "points": "[[0,0,0],[0,0,1]]", "properties": '{"a": 1}'})
        self.assertTrue(result.success, result.error)
        validated = result.data["input"]
        self.assertEqual(validated.points, [[0.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        self.assertEqual(validated.properties, {"a": 1})


if __name__ == "__main__":
    unittest.main()
