from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.inspectors.scene_inspector import SceneInspector
from .fakes import FakeBridge, FakeObject


class TestSceneInspector(unittest.TestCase):

    def test_inspect_empty_scene(self):
        bridge = FakeBridge(scene_name="EmptyScene", objects=[])
        inspector = SceneInspector(bridge)

        result = inspector.inspect()

        self.assertEqual(result["scene"]["name"], "EmptyScene")
        self.assertEqual(result["objects"], [])

    def test_inspect_mesh_object_has_rotation_and_scale(self):
        cube = FakeObject(name="Cube", type_="MESH", location=[1, 2, 3])
        bridge = FakeBridge(objects=[cube])
        inspector = SceneInspector(bridge)

        result = inspector.inspect()
        obj_data = result["objects"][0]

        self.assertEqual(obj_data["name"], "Cube")
        self.assertEqual(obj_data["location"], [1, 2, 3])
        self.assertIn("rotation", obj_data)
        self.assertIn("scale", obj_data)

    def test_non_mesh_object_has_no_rotation_scale(self):
        camera = FakeObject(name="Camera", type_="CAMERA")
        bridge = FakeBridge(objects=[camera])
        inspector = SceneInspector(bridge)

        result = inspector.inspect()
        obj_data = result["objects"][0]

        self.assertNotIn("rotation", obj_data)
        self.assertNotIn("scale", obj_data)


if __name__ == "__main__":
    unittest.main()