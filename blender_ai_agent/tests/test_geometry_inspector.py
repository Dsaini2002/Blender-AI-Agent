from . import _bpy_stub  # noqa: F401

import unittest

from blender_ai_agent.qa.geometry_inspector import GeometryInspector
from blender_ai_agent.qa.models import Severity
from .fakes import FakeBridge, FakeObject


class TestGeometryInspector(unittest.TestCase):

    def test_clean_scene_has_no_issues(self):
        bridge = FakeBridge(objects=[FakeObject(name="Cube", location=[0, 0, 0])])
        inspector = GeometryInspector(bridge)

        issues = inspector.inspect()

        self.assertEqual(issues, [])

    def test_non_manifold_mesh_is_high_severity_and_not_auto_fixable(self):
        obj = FakeObject(name="Cube", non_manifold_edge_count=3)
        bridge = FakeBridge(objects=[obj])
        inspector = GeometryInspector(bridge)

        issues = inspector.inspect()

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_type, "non_manifold_geometry")
        self.assertEqual(issues[0].severity, Severity.HIGH)
        self.assertFalse(issues[0].auto_fixable)

    def test_flipped_normals_are_medium_severity_and_auto_fixable(self):
        obj = FakeObject(name="Cube", flipped_normal_count=6)
        bridge = FakeBridge(objects=[obj])
        inspector = GeometryInspector(bridge)

        issues = inspector.inspect()

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].issue_type, "flipped_normals")
        self.assertEqual(issues[0].severity, Severity.MEDIUM)
        self.assertTrue(issues[0].auto_fixable)

    def test_overlapping_objects_are_detected(self):
        obj_a = FakeObject(name="CubeA", location=[0, 0, 0], bounding_box_size=2.0)
        obj_b = FakeObject(name="CubeB", location=[0.5, 0, 0], bounding_box_size=2.0)
        bridge = FakeBridge(objects=[obj_a, obj_b])
        inspector = GeometryInspector(bridge)

        issues = inspector.inspect()

        overlap_issues = [i for i in issues if i.issue_type == "intersecting_geometry"]
        self.assertEqual(len(overlap_issues), 1)
        self.assertTrue(overlap_issues[0].auto_fixable)

    def test_non_overlapping_objects_produce_no_intersection_issue(self):
        obj_a = FakeObject(name="CubeA", location=[0, 0, 0], bounding_box_size=1.0)
        obj_b = FakeObject(name="CubeB", location=[10, 0, 0], bounding_box_size=1.0)
        bridge = FakeBridge(objects=[obj_a, obj_b])
        inspector = GeometryInspector(bridge)

        issues = inspector.inspect()

        self.assertEqual(issues, [])

    def test_non_mesh_objects_are_ignored(self):
        camera = FakeObject(name="Camera", type_="CAMERA")
        bridge = FakeBridge(objects=[camera])
        inspector = GeometryInspector(bridge)

        issues = inspector.inspect()

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
