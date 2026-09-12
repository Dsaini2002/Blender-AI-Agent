from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.tools.animation_tools import InsertKeyframeTool
from .fakes import FakeBridge, FakeObject


class TestInsertKeyframeTool(unittest.TestCase):

    def test_insert_keyframe_success(self):
        bridge = FakeBridge(objects=[FakeObject(name="Ball")])
        tool = InsertKeyframeTool(bridge)

        result = tool.execute({"object_name": "Ball", "frame": 1})

        self.assertTrue(result.success)
        self.assertIn(1, bridge.get_keyframes("Ball"))

    def test_insert_keyframe_with_location(self):
        bridge = FakeBridge(objects=[FakeObject(name="Ball")])
        tool = InsertKeyframeTool(bridge)

        tool.execute({"object_name": "Ball", "frame": 20, "location": [0, 0, 5]})

        self.assertEqual(bridge.get_object("Ball").location, [0, 0, 5])

    def test_missing_object_fails_gracefully(self):
        bridge = FakeBridge(objects=[])
        tool = InsertKeyframeTool(bridge)

        result = tool.execute({"object_name": "DoesNotExist", "frame": 1})

        self.assertFalse(result.success)

    def test_negative_frame_fails_validation(self):
        bridge = FakeBridge(objects=[FakeObject(name="Ball")])
        tool = InsertKeyframeTool(bridge)

        result = tool.execute({"object_name": "Ball", "frame": -5})

        self.assertFalse(result.success)


if __name__ == "__main__":
    unittest.main()