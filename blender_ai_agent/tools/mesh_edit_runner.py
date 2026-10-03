"""
mesh_edit_runner.py
====================
Hinglish: Imported model ke KAI mesh-hisse ho sakte hain (body + dhakkan...). Sab ko ek saath jod kar operators chalata hai
(taaki twist/bend/cut poore object par ek jaisa lage), phir natija wapas har hisse mein baant deta hai. Pure Python; bpy nahi.

parts  : [{"name", "vertices" (world), "faces"}]
return : har hisse ke liye {"name", "vertices", "faces", "face_source", "topology_changed", "removed_faces",
                            "orig_vertices", "orig_faces"}  + summary notes
"""

from typing import Any, Dict, List, Sequence, Tuple

from .mesh_engine import apply_ops, compact_mesh


def run_edit_on_parts(parts: Sequence[Dict[str, Any]], ops: Sequence[Dict[str, Any]], seed: int = 1) -> Tuple[List[Dict[str, Any]], List[str]]:
    if not parts:
        raise ValueError("no mesh to edit")

    vertices: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []
    v_ranges, f_ranges = [], []
    for part in parts:
        v_start, f_start = len(vertices), len(faces)
        vertices.extend(tuple(v) for v in part["vertices"])
        faces.extend([v_start + i for i in f] for f in part["faces"])
        v_ranges.append((v_start, len(vertices)))
        f_ranges.append((f_start, len(faces)))

    result = apply_ops(vertices, faces, ops, seed)

    def part_of_face(global_index: int) -> int:
        for p, (a, b) in enumerate(f_ranges):
            if a <= global_index < b:
                return p
        return -1

    outputs: List[Dict[str, Any]] = []
    if not result.topology_changed:
        removed_by_part: Dict[int, List[int]] = {p: [] for p in range(len(parts))}
        for g in result.removed_faces:
            p = part_of_face(g)
            if p >= 0:
                removed_by_part[p].append(g - f_ranges[p][0])
        for p, part in enumerate(parts):
            a, b = v_ranges[p]
            outputs.append({
                "name": part["name"], "vertices": result.vertices[a:b], "faces": part["faces"], "face_source": None,
                "topology_changed": False, "removed_faces": removed_by_part[p],
                "orig_vertices": len(part["vertices"]), "orig_faces": len(part["faces"]),
            })
        return outputs, result.notes

    # topology badli: faces ko unke asli hisse ke hisaab se baanto
    vertex_owner: Dict[int, int] = {}
    face_owner: List[int] = []
    for new_index, face in enumerate(result.faces):
        src = result.face_source[new_index]
        owner = part_of_face(src) if src >= 0 else -1
        face_owner.append(owner)
        if owner >= 0:
            for v in face:
                vertex_owner.setdefault(v, owner)
    for new_index, face in enumerate(result.faces):            # cap jaise bilkul naye faces: apne vertices ke malik ke saath
        if face_owner[new_index] < 0:
            owners = [vertex_owner[v] for v in face if v in vertex_owner]
            face_owner[new_index] = owners[0] if owners else 0

    for p, part in enumerate(parts):
        idx = [i for i, owner in enumerate(face_owner) if owner == p]
        part_faces = [result.faces[i] for i in idx]
        local_vertices, local_faces = compact_mesh(result.vertices, part_faces)
        local_source = []
        base = f_ranges[p][0]
        for i in idx:
            src = result.face_source[i]
            local_source.append(src - base if (src >= 0 and part_of_face(src) == p) else -1)
        outputs.append({
            "name": part["name"], "vertices": local_vertices, "faces": local_faces, "face_source": local_source,
            "topology_changed": True, "removed_faces": [],
            "orig_vertices": len(part["vertices"]), "orig_faces": len(part["faces"]),
        })
    return outputs, result.notes