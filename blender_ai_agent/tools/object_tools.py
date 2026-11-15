"""Object Tools"""

from .base import Permission, Tool, ToolResult
from .models import (
    CreateObjectInput,
    DeleteObjectInput,
    DuplicateObjectInput,
    RenameObjectInput,
    TransformObjectInput,
)


class CreateObjectTool(Tool):
    name = "object.create"
    auto_name = "Object"
    description = (
        "Creates a new object in the scene. Pass `object_type` (default MESH) and "
        "a matching `primitive`. Supported object_type -> primitive values: "
        "MESH -> CUBE, SPHERE, ICOSPHERE, CONE, CYLINDER, CIRCLE, PLANE, TORUS, GRID, MONKEY; "
        "CURVE -> BEZIER, CIRCLE, NURBS_CURVE, NURBS_CIRCLE, PATH; "
        "SURFACE -> NURBS_CURVE, NURBS_CIRCLE, NURBS_SURFACE, NURBS_CYLINDER, NURBS_SPHERE, NURBS_TORUS; "
        "METABALL -> BALL, CAPSULE, PLANE, ELLIPSOID, CUBE; "
        "EMPTY -> PLAIN_AXES, ARROWS, SINGLE_ARROW, CIRCLE, CUBE, SPHERE, CONE; "
        "LIGHT -> POINT, SUN, SPOT, AREA; "
        "ARMATURE -> ARMATURE; LATTICE -> LATTICE."
    )
    permission = Permission.SAFE_WRITE
    input_model = CreateObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: CreateObjectInput) -> ToolResult:
        obj = self._bridge.create_object(
            name=validated_input.name,
            object_type=validated_input.object_type,
            primitive=validated_input.primitive,
            location=validated_input.location,
        )
        return ToolResult.ok({
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
        })


class DeleteObjectTool(Tool):
    name = "object.delete"
    description = "Deletes objects from the scene: `name` for one object or `names` for several."
    permission = Permission.DESTRUCTIVE
    input_model = DeleteObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: DeleteObjectInput) -> ToolResult:
        if len(validated_input.names) == 1:
            deleted = self._bridge.delete_object(validated_input.name)
            if not deleted:
                return ToolResult.fail(f"Object '{validated_input.name}' not found in scene.")
            return ToolResult.ok({"deleted": validated_input.name})
        done, missing = [], []
        for name in validated_input.names:
            (done if self._bridge.delete_object(name) else missing).append(name)
        if not done:
            return ToolResult.fail(f"None of these objects exist: {', '.join(missing)}")
        data = {"deleted": done}
        if missing:
            data["not_found"] = missing
        return ToolResult.ok(data)


class DuplicateObjectTool(Tool):
    name = "object.duplicate"
    description = "Duplicates an existing object in the scene."
    permission = Permission.SAFE_WRITE
    input_model = DuplicateObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: DuplicateObjectInput) -> ToolResult:
        new_obj = self._bridge.duplicate_object(
            name=validated_input.name,
            new_name=validated_input.new_name or None,
        )

        if new_obj is None:
            return ToolResult.fail(f"Object '{validated_input.name}' not found in scene.")

        return ToolResult.ok({
            "original": validated_input.name,
            "duplicate": new_obj.name,
        })


class RenameObjectTool(Tool):
    name = "object.rename"
    description = "Renames an existing object in the scene."
    permission = Permission.SAFE_WRITE
    input_model = RenameObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: RenameObjectInput) -> ToolResult:
        obj = self._bridge.rename_object(validated_input.old_name, validated_input.new_name)

        if obj is None:
            return ToolResult.fail(f"Object '{validated_input.old_name}' not found in scene.")

        return ToolResult.ok({"old_name": validated_input.old_name, "new_name": obj.name})


class TransformObjectTool(Tool):
    name = "object.transform"
    description = "Updates location, rotation, and/or scale of an existing object."
    permission = Permission.SAFE_WRITE
    input_model = TransformObjectInput

    def __init__(self, bridge):
        self._bridge = bridge

    # A scale jump this big that also produces something this large is almost always a
    # mistake: imported models often carry scale 0.01, and "fixing" it to 1.0 makes
    # them 100x too big (a 2 m bench becomes a 200 m wall).
    MAX_SCALE_JUMP = 20.0
    IMPORT_SCALE_BELOW = 0.2       # only objects carrying a tiny import scale (0.01, 0.1) are guarded
    MAX_RESULT_SIZE_M = 40.0

    def _oversize_reason(self, name, new_scale):
        get_object = getattr(self._bridge, "get_object", None)
        measure = getattr(self._bridge, "measure_objects", None)
        if get_object is None or measure is None or new_scale is None:
            return None
        try:
            obj = get_object(name)
            if obj is None:
                return None
            old = [abs(float(v)) for v in obj.scale]
            box = measure([name])
        except Exception:  # noqa: BLE001
            return None
        if not box or any(v < 1e-9 for v in old):
            return None
        if min(old) >= self.IMPORT_SCALE_BELOW:
            return None   # a normal object (e.g. a fresh 2 m cube) being sized up: that is ordinary modelling
        ratios = [abs(float(n)) / o for n, o in zip(new_scale, old)]
        jump = max(ratios)
        if jump < self.MAX_SCALE_JUMP:
            return None
        size = [box["max"][k] - box["min"][k] for k in range(3)]
        new_size = [size[k] * ratios[k] for k in range(3)]
        biggest = max(new_size)
        if biggest <= self.MAX_RESULT_SIZE_M:
            return None
        if new_size[2] < 0.05 * max(new_size[0], new_size[1]):
            return None   # flat ground / water plane: big is fine
        return (f"Refused: this scale would make '{name}' {jump:.0f}x bigger "
                f"({max(size):.2f} m -> {biggest:.0f} m). Its current scale {[round(v, 4) for v in obj.scale]} "
                f"already gives its real size (imported models often use 0.01). Leave 'scale' out to keep the "
                f"size, or use object.measure and scale relative to the current value.")

    def run(self, validated_input: TransformObjectInput) -> ToolResult:
        reason = self._oversize_reason(validated_input.name, validated_input.scale)
        if reason:
            return ToolResult.fail(reason)
        obj = self._bridge.transform_object(
            name=validated_input.name,
            location=validated_input.location,
            rotation=validated_input.rotation,
            scale=validated_input.scale,
        )

        if obj is None:
            return ToolResult.fail(f"Object '{validated_input.name}' not found in scene.")

        return ToolResult.ok({
            "name": obj.name,
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
        })