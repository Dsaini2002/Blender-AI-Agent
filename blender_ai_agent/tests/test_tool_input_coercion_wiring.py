from . import _bpy_stub  # noqa: F401

import unittest
from dataclasses import dataclass
from typing import List, Optional

from blender_ai_agent.tools.base import Permission, Tool, ToolResult
from blender_ai_agent.tools.models import CreateMaterialInput, TransformObjectInput
from .test_lighting_tools import FakeMapComposite, FakeRepeatedComposite


@dataclass
class EchoInput:
    name: str
    location: Optional[List[float]] = None
    count: int = 1
    flag: bool = False


class EchoTool(Tool):
    name = "test.echo"
    description = "echo"
    permission = Permission.READ_ONLY
    input_model = EchoInput

    def run(self, validated_input):
        return ToolResult.ok({"name": validated_input.name, "location": validated_input.location,
                              "count": validated_input.count, "flag": validated_input.flag})


class TransformEchoTool(Tool):
    name = "test.transform"
    input_model = TransformObjectInput

    def run(self, validated_input):
        return ToolResult.ok({"location": validated_input.location, "scale": validated_input.scale})


class MaterialEchoTool(Tool):
    name = "test.material"
    input_model = CreateMaterialInput

    def run(self, validated_input):
        return ToolResult.ok({"color": validated_input.color})


class BrokenPostInit:
    """__post_init__ andar kisi galat type par AttributeError/KeyError uthata hai."""

    def __init__(self, name, thing=None):
        self.name = name
        self.thing = thing.nonexistent_attribute          # AttributeError


class AttributeErrorTool(Tool):
    name = "test.broken"
    input_model = None

    def run(self, validated_input):
        return ToolResult.ok({})


class NoInputTool(Tool):
    name = "test.noinput"

    def run(self, validated_input):
        return ToolResult.ok({"got": validated_input})


class TestCoercionIsWiredIntoEveryTool(unittest.TestCase):

    def test_llm_style_arguments_just_work(self):
        result = EchoTool().execute({"name": "A", "location": "1, 2, 3", "count": "3", "flag": "true"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data, {"name": "A", "location": [1, 2, 3], "count": 3, "flag": True})

    def test_floats_dicts_and_proto_containers(self):
        self.assertEqual(EchoTool().execute({"name": "A", "count": 640.0}).data["count"], 640)
        self.assertEqual(EchoTool().execute({"name": "A", "location": {"x": 1, "y": 2, "z": 3}}).data["location"], [1, 2, 3])
        result = EchoTool().execute(FakeMapComposite({"name": "A", "location": FakeRepeatedComposite(["1", "2", "3"])}))
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["location"], [1, 2, 3])

    def test_aliases_and_coercion_work_together(self):
        result = EchoTool().execute({"name": "A", "position": "4, 5, 6", "mystery_key": "dropped"})
        self.assertTrue(result.success, result.error)
        self.assertEqual(result.data["location"], [4, 5, 6])

    def test_real_models_are_fixed_centrally(self):
        out = TransformEchoTool().execute({"name": "A", "location": "1, 2, 3", "scale": ["2", "2", "2"]})
        self.assertEqual(out.data, {"location": [1, 2, 3], "scale": [2, 2, 2]})
        mat = MaterialEchoTool().execute({"name": "Sofa", "color": ["0.35", "0.45", "0.65"]})
        self.assertTrue(mat.success, mat.error)
        self.assertEqual(mat.data["color"], [0.35, 0.45, 0.65])

    def test_unusable_values_still_give_a_clean_failure(self):
        for bad in ({"name": "A", "location": "nope"}, {"name": "A", "count": "many"}, {}):
            result = EchoTool().execute(bad)
            self.assertIsInstance(result, ToolResult)

        failed = TransformEchoTool().execute({"name": "A", "location": "1, 2"})
        self.assertFalse(failed.success)
        self.assertIn("must have exactly 3 values", failed.error)

    def test_a_crash_inside_post_init_becomes_a_failure_not_an_exception(self):
        @dataclass
        class Sneaky:
            name: str
            value: int = 0

            def __post_init__(self):
                if self.value == 99:
                    raise AttributeError("'NoneType' object has no attribute 'foo'")

        class SneakyTool(Tool):
            name = "test.sneaky"
            input_model = Sneaky

            def run(self, validated_input):
                return ToolResult.ok({})

        result = SneakyTool().execute({"name": "A", "value": 99})
        self.assertFalse(result.success)
        self.assertIn("Invalid input for tool 'test.sneaky'", result.error)

    def test_tools_without_an_input_model_are_unchanged(self):
        self.assertEqual(NoInputTool().execute({"a": 1}).data, {"got": {"a": 1}})
        self.assertEqual(NoInputTool().execute().data, {"got": {}})

    def test_existing_validation_messages_are_unchanged(self):
        result = TransformEchoTool().execute({"name": "A"})
        self.assertFalse(result.success)
        self.assertIn("requires at least one of: location, rotation, scale", result.error)
        missing = EchoTool().execute({"location": [1, 2, 3]})
        self.assertFalse(missing.success)
        self.assertIn("Invalid input for tool 'test.echo'", missing.error)

    def test_run_errors_still_become_failures(self):
        class Boom(Tool):
            name = "test.boom"

            def run(self, validated_input):
                raise RuntimeError("kaboom")

        result = Boom().execute({})
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Tool 'test.boom' failed: kaboom")


if __name__ == "__main__":
    unittest.main()