from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.advanced.context_optimizer import ContextOptimizer
from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge, FakeObject


def build_optimizer(objects):
    bridge = FakeBridge(objects=objects)
    inspector = SceneInspector(bridge)
    tool = SceneInspectTool(inspector)
    context_manager = ContextManager(tool)
    return ContextOptimizer(context_manager)


class TestContextOptimizer(unittest.TestCase):

    def test_with_selection_returns_focused_context(self):
        optimizer = build_optimizer(objects=[FakeObject(name="Sword"), FakeObject(name="Shield")])

        context = optimizer.build_optimized_context(selected_object_names=["Sword"])

        self.assertIn("focused_objects", context)
        self.assertEqual(len(context["focused_objects"]), 1)

    def test_without_selection_returns_summary(self):
        optimizer = build_optimizer(objects=[FakeObject(name="Sword"), FakeObject(name="Shield")])

        context = optimizer.build_optimized_context()

        self.assertIn("objects_summary", context)
        self.assertEqual(context["object_count"], 2)

    def test_estimate_context_size_for_focused(self):
        optimizer = build_optimizer(objects=[FakeObject(name="Sword")])
        context = optimizer.build_optimized_context(selected_object_names=["Sword"])

        self.assertEqual(optimizer.estimate_context_size(context), 1)

    def test_estimate_context_size_for_summary(self):
        optimizer = build_optimizer(objects=[FakeObject(name="A"), FakeObject(name="B"), FakeObject(name="C")])
        context = optimizer.build_optimized_context()

        self.assertEqual(optimizer.estimate_context_size(context), 3)


if __name__ == "__main__":
    unittest.main()