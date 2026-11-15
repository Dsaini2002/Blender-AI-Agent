"""ToolCaller"""

from typing import List

from ..agent.models import ToolCall, ToolDefinition
from ..tools.base import ToolResult


class ToolCaller:

    def __init__(self, registry):
        self._registry = registry
        # Optional gate for risky tools: approver(tool_call, tool) -> None to allow, or a reason string to refuse.
        # The Blender UI sets it while a request runs (asks the user); tests and scripts leave it unset.
        self.approver = None

    def get_tool_definitions(self) -> List[ToolDefinition]:
        definitions = []
        for tool_name in self._registry.list_tools():
            tool = self._registry.get(tool_name)
            definitions.append(ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=self._build_parameters_schema(tool),
            ))
        return definitions

    def has_tool(self, tool_name: str) -> bool:
        return tool_name in self._registry.list_tools()

    _NAME_PREFIXES = ("call:", "call_", "functions.", "function.", "default_api.", "tools.", "tool:", "api.")

    def _resolve(self, name: str):
        """The tool, also when a model wrote 'call:mesh.boundary_wall', 'functions.mesh.building' or
        'mesh__building'."""
        try:
            return self._registry.get(name)
        except KeyError:
            pass
        candidates = [str(name or "").strip()]
        changed = True
        while changed:
            changed = False
            for prefix in self._NAME_PREFIXES:
                if candidates[-1].startswith(prefix):
                    candidates.append(candidates[-1][len(prefix):])
                    changed = True
        candidates.append(candidates[-1].replace("__", "."))
        for candidate in candidates[1:]:
            try:
                return self._registry.get(candidate)
            except KeyError:
                continue
        raise KeyError(name)

    def call(self, tool_call: ToolCall) -> ToolResult:
        try:
            from ..copilot import activity
            if activity.should_stop():
                # Stop was pressed: from now on the run changes nothing more in the scene
                return ToolResult.fail("Stopped by user - this step was not run.")
        except ImportError:
            pass
        try:
            tool = self._resolve(tool_call.tool_name)
        except KeyError:
            return ToolResult.fail(f"Unknown tool: '{tool_call.tool_name}'")

        approver = self.approver
        if approver is not None:
            try:
                refusal = approver(tool_call, tool)
            except Exception as exc:  # noqa: BLE001
                refusal = f"approval check failed ({exc})"
            if refusal:
                return ToolResult.fail(f"Not run: {refusal}. Do not retry this call; continue without it or ask the user.")

        return tool.execute(tool_call.arguments)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _build_parameters_schema(self, tool) -> dict:
        """Real JSON Schema from the tool's input dataclass (nested lists, objects, optional fields)."""
        if tool.input_model is None:
            return {"type": "object", "properties": {}}

        import dataclasses
        import typing

        try:
            type_fields = dataclasses.fields(tool.input_model)
        except TypeError:
            return {"type": "object", "properties": {}}
        try:
            hints = typing.get_type_hints(tool.input_model)
        except Exception:  # noqa: BLE001
            hints = {}

        properties = {}
        required = []
        for field in type_fields:
            if field.name.startswith("_"):
                continue
            schema = self._python_type_to_json_schema(hints.get(field.name, field.type))
            description = (field.metadata or {}).get("description") if hasattr(field, "metadata") else None
            if description:
                schema = dict(schema, description=description)
            properties[field.name] = schema
            if field.default is dataclasses.MISSING and field.default_factory is dataclasses.MISSING:
                required.append(field.name)

        schema = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    @staticmethod
    def _python_type_to_json_schema(python_type) -> dict:
        """Python type hint -> JSON Schema (recursive)."""
        import typing

        if isinstance(python_type, str):                      # postponed annotation that could not be resolved
            lowered = python_type.lower()
            if "list" in lowered or "tuple" in lowered:
                return {"type": "array", "items": {"type": "number"}}
            for name, kind in (("bool", "boolean"), ("int", "integer"), ("float", "number"), ("str", "string")):
                if name in lowered:
                    return {"type": kind}
            return {}

        origin = typing.get_origin(python_type)
        args = typing.get_args(python_type)

        if origin is typing.Union:
            options = [a for a in args if a is not type(None)]
            if len(options) == 1:
                return ToolCaller._python_type_to_json_schema(options[0])
            return {}
        if python_type is bool:
            return {"type": "boolean"}
        if python_type is int:
            return {"type": "integer"}
        if python_type is float:
            return {"type": "number"}
        if python_type is str:
            return {"type": "string"}
        if python_type in (list, tuple) or origin in (list, tuple, typing.Sequence):
            element = args[0] if args else typing.Any
            items = ToolCaller._python_type_to_json_schema(element)
            return {"type": "array", "items": items or {}}
        if python_type is dict or origin is dict:
            return {"type": "object"}
        return {}                                              # typing.Any: any JSON value
