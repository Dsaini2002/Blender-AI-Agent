import dataclasses
import unittest
from typing import Dict, List, Optional

from blender_ai_agent.input_coercion import coerce_arguments, coerce_value, to_plain
from blender_ai_agent.tools.models import (
    CreateMaterialInput, CreateObjectInput, PlaceModelInput, RenderPreviewInput, TransformObjectInput,
)
from .test_lighting_tools import FakeMapComposite, FakeRepeatedComposite


@dataclasses.dataclass
class Sample:
    name: str
    count: int = 1
    ratio: float = 0.5
    flag: bool = False
    location: Optional[List[float]] = None
    points: Optional[List[List[float]]] = None
    tags: Optional[List[str]] = None
    extra: Optional[Dict[str, float]] = None


class TestCoerceValue(unittest.TestCase):

    def test_numbers(self):
        self.assertEqual(coerce_value("640", int), 640)
        self.assertEqual(coerce_value(640.0, int), 640)
        self.assertEqual(coerce_value("640.0", int), 640)
        self.assertEqual(coerce_value("0.5", float), 0.5)
        self.assertEqual(coerce_value(3, float), 3)
        self.assertIs(coerce_value(True, int), True)                    # bool ko number nahi banate

    def test_bools(self):
        for text, expected in (("true", True), ("False", False), ("yes", True), ("no", False), ("1", True), ("0", False)):
            self.assertIs(coerce_value(text, bool), expected, text)
        self.assertIs(coerce_value(1, bool), True)
        self.assertEqual(coerce_value("maybe", bool), "maybe")           # samajh na aaye -> jaisa hai

    def test_str_field_gets_number_as_text(self):
        self.assertEqual(coerce_value(5, str), "5")
        self.assertEqual(coerce_value("abc", str), "abc")

    def test_vectors(self):
        for value in ("1, 2, 3", "[1, 2, 3]", "(1 2 3)", "1;2;3", ["1", "2", "3"], (1, 2, 3),
                      {"x": 1, "y": 2, "z": 3}, {"X": "1", "Y": "2", "Z": "3"},
                      FakeRepeatedComposite(["1", "2", "3"]), FakeMapComposite({"x": 1, "y": 2, "z": 3})):
            self.assertEqual(coerce_value(value, List[float]), [1, 2, 3], repr(value))

    def test_rgb_dict_becomes_a_list(self):
        self.assertEqual(coerce_value({"r": "1", "g": "0.5", "b": "0"}, List[float]), [1, 0.5, 0])

    def test_nested_lists(self):
        self.assertEqual(coerce_value([["0", "0", "0"], "1, 2, 3"], List[List[float]]), [[0, 0, 0], [1, 2, 3]])

    def test_string_list(self):
        self.assertEqual(coerce_value("Cube", List[str]), ["Cube"])
        self.assertEqual(coerce_value(["a", 5], List[str]), ["a", "5"])

    def test_unusable_values_are_left_alone_never_raise(self):
        self.assertEqual(coerce_value("nope", List[float]), "nope")
        self.assertEqual(coerce_value({"a": 1}, List[float]), {"a": 1})
        self.assertEqual(coerce_value(object, int), object)
        self.assertIsNone(coerce_value(None, int))

    def test_optional_and_union_syntax(self):
        self.assertEqual(coerce_value("5", Optional[int]), 5)
        self.assertEqual(coerce_value("1, 2, 3", Optional[List[float]]), [1, 2, 3])

    def test_dict_fields_are_not_touched(self):
        self.assertEqual(coerce_value({"a": "1"}, Dict[str, float]), {"a": "1"})


class TestCoerceArguments(unittest.TestCase):

    def test_whole_argument_dict(self):
        result = coerce_arguments(Sample, {
            "name": "A", "count": "3", "ratio": "0.25", "flag": "true", "location": "1, 2, 3",
            "points": [["0", "0", "0"], ["1", "1", "1"]], "tags": "x", "extra": {"k": "v"},
        })
        self.assertEqual(result, {"name": "A", "count": 3, "ratio": 0.25, "flag": True, "location": [1, 2, 3],
                                  "points": [[0, 0, 0], [1, 1, 1]], "tags": ["x"], "extra": {"k": "v"}})

    def test_unknown_keys_pass_through_and_input_is_not_mutated(self):
        original = {"name": "A", "mystery": "keep me", "count": "2"}
        result = coerce_arguments(Sample, original)
        self.assertEqual(result["mystery"], "keep me")
        self.assertEqual(original["count"], "2")

    def test_proto_arguments_become_plain(self):
        result = coerce_arguments(Sample, FakeMapComposite({"name": "A", "location": FakeRepeatedComposite([1, 2, 3])}))
        self.assertEqual(result, {"name": "A", "location": [1, 2, 3]})
        self.assertIsInstance(result["location"], list)

    def test_non_dataclass_or_empty_input(self):
        self.assertEqual(coerce_arguments(None, {"a": FakeRepeatedComposite([1])}), {"a": [1]})
        self.assertEqual(coerce_arguments(dict, {"a": 1}), {"a": 1})
        self.assertEqual(coerce_arguments(Sample, None), {})
        self.assertEqual(coerce_arguments(Sample, {}), {})

    def test_to_plain_is_exported_and_idempotent(self):
        data = {"a": [1, (2, 3)], "b": None}
        self.assertEqual(to_plain(to_plain(data)), {"a": [1, [2, 3]], "b": None})


class TestWithTheRealToolInputs(unittest.TestCase):
    """Log-style failures, fixed centrally for any tool input model."""

    def test_transform_object(self):
        args = coerce_arguments(TransformObjectInput, {"name": "A", "location": "1, 2, 3", "scale": ["2", "2", "2"]})
        data = TransformObjectInput(**args)
        self.assertEqual((data.location, data.scale), ([1, 2, 3], [2, 2, 2]))

    def test_create_object(self):
        args = coerce_arguments(CreateObjectInput, {"name": "A", "location": {"x": "1", "y": "2", "z": "3"}})
        self.assertEqual(CreateObjectInput(**args).location, [1, 2, 3])

    def test_create_material_with_string_colour(self):
        args = coerce_arguments(CreateMaterialInput, {"name": "Sofa", "color": ["0.35", "0.45", "0.65"]})
        self.assertEqual(args["color"], [0.35, 0.45, 0.65])
        self.assertTrue(all(isinstance(c, float) for c in CreateMaterialInput(**args).color))

    def test_render_preview(self):
        args = coerce_arguments(RenderPreviewInput, {"filepath": "a.png", "width": "640", "draft": "true"})
        self.assertEqual((args["width"], args["draft"]), (640, True))
        self.assertEqual(RenderPreviewInput(**args).resolution(), (640, 360))

    def test_place_model_with_mixed_junk(self):
        args = coerce_arguments(PlaceModelInput, {"model": "campfire", "location": "0, 0, 0", "scale": "2",
                                                   "yaw_degrees": "90"})
        data = PlaceModelInput(**args)
        self.assertEqual((data.location, data.scale, data.yaw_degrees), ([0, 0, 0], 2, 90))


if __name__ == "__main__":
    unittest.main()