from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.agent.context import ContextManager
from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from blender_ai_agent.tools.scene_tools import SceneInspectTool
from .fakes import FakeBridge, FakeObject


def build_context_manager(objects=None):
    bridge = FakeBridge(objects=objects or [])
    inspector = SceneInspector(bridge)
    tool = SceneInspectTool(inspector)
    return ContextManager(tool)


class TestContextManagerSummary(unittest.TestCase):

    def test_empty_scene_summary(self):
        cm = build_context_manager(objects=[])
        context = cm.build_context()

        self.assertEqual(context["object_count"], 0)
        self.assertEqual(context["objects_summary"], [])

    def test_summary_has_name_and_type_only(self):
        cube = FakeObject(name="Cube", type_="MESH")
        cm = build_context_manager(objects=[cube])
        context = cm.build_context()

        self.assertEqual(context["object_count"], 1)
        summary_obj = context["objects_summary"][0]
        self.assertEqual(summary_obj, {"name": "Cube", "type": "MESH"})
        # location/rotation/scale summary mein NAHI hone chahiye
        self.assertNotIn("location", summary_obj)

    def test_multiple_objects_counted(self):
        objects = [FakeObject(name=f"Obj{i}") for i in range(5)]
        cm = build_context_manager(objects=objects)
        context = cm.build_context()

        self.assertEqual(context["object_count"], 5)


class TestContextManagerFocused(unittest.TestCase):

    def test_focused_object_has_full_detail(self):
        cube = FakeObject(name="Cube", type_="MESH", location=[1, 2, 3])
        cm = build_context_manager(objects=[cube])
        context = cm.build_context(focus_object_names=["Cube"])

        self.assertEqual(len(context["focused_objects"]), 1)
        focused = context["focused_objects"][0]
        self.assertEqual(focused["location"], [1, 2, 3])
        self.assertIn("rotation", focused)  # full detail milna chahiye

    def test_focused_missing_object_reported(self):
        cm = build_context_manager(objects=[])
        context = cm.build_context(focus_object_names=["DoesNotExist"])

        self.assertEqual(context["focused_objects"], [])
        self.assertEqual(context["not_found"], ["DoesNotExist"])

    def test_focused_ignores_unrelated_objects(self):
        cube = FakeObject(name="Cube")
        sphere = FakeObject(name="Sphere")
        cm = build_context_manager(objects=[cube, sphere])
        context = cm.build_context(focus_object_names=["Cube"])

        names = [obj["name"] for obj in context["focused_objects"]]
        self.assertEqual(names, ["Cube"])


if __name__ == "__main__":
    unittest.main()