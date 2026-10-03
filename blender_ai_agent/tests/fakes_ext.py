"""
fakes_ext.py
=============
Hinglish: tests/fakes.py ka FakeBridge jaisa hai waisa hi rehta hai — ye uske upar 2 cheezein jodta hai
jo naye features ke tests ko chahiye:

  1. create_object() mein Blender jaisa naam-takkar suffix (.001) — library.place ke tests ke liye
  2. create_curve()  — curve.create / library.place (flames, ropes, branches) ke tests ke liye

Naye tests `from .fakes_ext import FakeBridge` karte hain. Purane tests `.fakes` se chalte rahenge.
"""

from .fakes import FakeBridge as _BaseFakeBridge
from .fakes import FakeObject


class FakeBridge(_BaseFakeBridge):

    def create_object(self, name, object_type="MESH", primitive="CUBE", location=None):
        existing = {o.name for o in self._objects}
        final_name, suffix = name, 0
        while final_name in existing:  # Blender-style .001 collision suffix, jaise asli bridge mein
            suffix += 1
            final_name = f"{name}.{suffix:03d}"
        obj = FakeObject(name=final_name, type_=object_type, location=location or [0.0, 0.0, 0.0])
        self._objects.append(obj)
        return obj

    def create_curve(self, name, points, curve_type="BEZIER", thickness=0.05, closed=False,
                     location=None, rotation=None, scale=None, fill_caps=True, resolution=12):
        existing = {o.name for o in self._objects}
        final_name, suffix = name, 0
        while final_name in existing:
            suffix += 1
            final_name = f"{name}.{suffix:03d}"

        obj = FakeObject(name=final_name, type_="CURVE",
                         location=list(location) if location else [0.0, 0.0, 0.0],
                         rotation=list(rotation) if rotation else [0.0, 0.0, 0.0])
        if scale is not None:
            obj.scale = list(scale)
        obj.curve_points = [list(p) for p in points]
        obj.curve_type = curve_type
        obj.thickness = thickness
        obj.closed = closed
        self._objects.append(obj)
        return obj

    def create_mesh(self, name, vertices, faces, location=None, rotation=None, scale=None, shade_smooth=False):
        existing = {o.name for o in self._objects}
        final_name, suffix = name, 0
        while final_name in existing:
            suffix += 1
            final_name = f"{name}.{suffix:03d}"

        obj = FakeObject(name=final_name, type_="MESH",
                         location=list(location) if location else [0.0, 0.0, 0.0],
                         rotation=list(rotation) if rotation else [0.0, 0.0, 0.0])
        if scale is not None:
            obj.scale = list(scale)
        obj.mesh_vertices = [list(v) for v in vertices]
        obj.mesh_faces = [list(f) for f in faces]
        obj.shade_smooth = shade_smooth
        self._objects.append(obj)
        return obj

    def damage_mesh(self, object_name, region="top", portion=0.25, strength=0.15, style="broken", seed=1, detail=1):
        obj = self.get_object(object_name)
        if obj is None or obj.type not in ("MESH", "EMPTY"):
            return None
        obj.damage = {"region": region, "portion": portion, "strength": strength, "style": style,
                      "seed": seed, "detail": detail}
        return {"object": obj.name, "meshes": [obj.name], "affected_vertices": 40, "moved_vertices": 40,
                "removed_faces": 3}

    def snapshot_mesh(self, object_name):
        obj = self.get_object(object_name)
        if obj is None or obj.type != "MESH":
            return None
        cube_vertices = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)]
        cube_faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
        vertices = getattr(obj, "mesh_vertices", None) or cube_vertices
        faces = getattr(obj, "mesh_faces", None) or cube_faces
        return {"root": obj.name, "parts": [{"name": obj.name, "vertices": [tuple(v) for v in vertices],
                                             "faces": [list(f) for f in faces]}]}

    def apply_mesh_edit(self, results):
        summary = {"meshes": [], "strategy": [], "uv_preserved": True, "removed_faces": 0, "vertex_count": 0, "face_count": 0}
        for item in results:
            obj = self.get_object(item["name"])
            if obj is None:
                continue
            faces = [list(f) for f in item["faces"]]
            if not item["topology_changed"] and item["removed_faces"]:
                gone = set(item["removed_faces"])
                faces = [f for i, f in enumerate(faces) if i not in gone]
                summary["removed_faces"] += len(gone)
            if item["topology_changed"]:
                summary["uv_preserved"] = False
            obj.mesh_vertices = [list(v) for v in item["vertices"]]
            obj.mesh_faces = faces
            obj.edited = item
            summary["meshes"].append(obj.name)
            summary["strategy"].append("rebuilt" if item["topology_changed"] else "moved vertices")
            summary["vertex_count"] += len(item["vertices"])
            summary["face_count"] += len(faces)
        return summary