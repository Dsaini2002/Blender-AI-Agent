"""
GeometryInspector — Step 12.3
=================================
Hinglish: Phase 12 ka MVP scope — sirf GEOMETRY checks (topology,
normals, intersecting objects). UV/Materials/Animation inspectors
baad mein isi Inspector pattern follow karke add honge.

Checks:
  1. Non-manifold geometry  -> HIGH severity, not auto-fixable (MVP mein)
  2. Flipped normals        -> MEDIUM severity, auto-fixable
  3. Intersecting objects   -> MEDIUM severity, auto-fixable (bounding-box heuristic)

MVP mein bounding-box overlap ek HEURISTIC hai (asli mesh-level
intersection check nahi) — false positives possible hain do objects
ke bounding boxes touch karne par bhi jab actual geometry overlap na
ho. Yeh limitation README/CHANGELOG mein documented honi chahiye.
"""

from typing import List

from .base import Inspector
from .models import Issue, Severity


class GeometryInspector(Inspector):
    name = "geometry"
    description = "Checks mesh objects for non-manifold geometry, flipped normals, and bounding-box overlaps."

    def inspect(self) -> List[Issue]:
        issues: List[Issue] = []
        mesh_objects = [obj for obj in self._bridge.get_objects() if obj.type == "MESH"]

        for obj in mesh_objects:
            stats = self._bridge.get_mesh_stats(obj.name)
            if stats is None:
                continue
            issues.extend(self._check_mesh_stats(obj.name, stats))

        issues.extend(self._check_intersections(mesh_objects))
        return issues

    # ---------------------------------------------------------
    # Per-object checks
    # ---------------------------------------------------------
    def _check_mesh_stats(self, object_name: str, stats: dict) -> List[Issue]:
        issues: List[Issue] = []

        non_manifold_count = stats.get("non_manifold_edge_count", 0)
        if non_manifold_count > 0:
            issues.append(Issue(
                object_name=object_name,
                issue_type="non_manifold_geometry",
                severity=Severity.HIGH,
                message=f"{non_manifold_count} non-manifold edge(s) found — mesh is not watertight.",
                auto_fixable=False,
            ))

        flipped_count = stats.get("flipped_normal_count", 0)
        if flipped_count > 0:
            issues.append(Issue(
                object_name=object_name,
                issue_type="flipped_normals",
                severity=Severity.MEDIUM,
                message=f"{flipped_count} face(s) appear to have flipped/inverted normals.",
                auto_fixable=True,
            ))

        return issues

    # ---------------------------------------------------------
    # Cross-object checks
    # ---------------------------------------------------------
    def _check_intersections(self, mesh_objects) -> List[Issue]:
        issues: List[Issue] = []
        stats_by_name = {}
        for obj in mesh_objects:
            stats = self._bridge.get_mesh_stats(obj.name)
            if stats is not None:
                stats_by_name[obj.name] = stats

        names = list(stats_by_name.keys())
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                name_a, name_b = names[i], names[j]
                if self._bounding_boxes_overlap(stats_by_name[name_a], stats_by_name[name_b]):
                    issues.append(Issue(
                        object_name=name_a,
                        issue_type="intersecting_geometry",
                        severity=Severity.MEDIUM,
                        message=f"'{name_a}' bounding box overlaps with '{name_b}'.",
                        auto_fixable=True,
                    ))

        return issues

    @staticmethod
    def _bounding_boxes_overlap(stats_a: dict, stats_b: dict) -> bool:
        min_a, max_a = stats_a["bounding_box_min"], stats_a["bounding_box_max"]
        min_b, max_b = stats_b["bounding_box_min"], stats_b["bounding_box_max"]

        for axis in range(3):
            if max_a[axis] < min_b[axis] or max_b[axis] < min_a[axis]:
                return False  # kisi bhi axis par gap hai -> overlap nahi
        return True
