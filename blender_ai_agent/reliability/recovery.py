"""RecoveryManager"""

from typing import Optional

from ..agent.models import ToolCall
from .errors import ErrorCode, ToolError


class RecoveryManager:

    NAME_ARG_KEYS = ("name", "object_name", "old_name")
    KNOWN_FIELDS = ("material_name", "modifier_name", "modifier_type", "new_name", "type")

    def __init__(self, tool_caller):
        self._tool_caller = tool_caller

    def attempt_recovery(self, tool_call: ToolCall, error: ToolError) -> Optional[ToolCall]:
        if error.code == ErrorCode.MISSING_ARGUMENT:
            return self._recover_missing_argument(tool_call)

        if error.code != ErrorCode.OBJECT_NOT_FOUND:
            return None

        arg_key = self._find_name_argument(tool_call)
        if arg_key is None:
            return None

        wrong_name = tool_call.arguments[arg_key]
        correct_name = self._find_similar_object_name(wrong_name)

        if correct_name is None:
            return None

        new_arguments = dict(tool_call.arguments)
        new_arguments[arg_key] = correct_name
        return ToolCall(tool_name=tool_call.tool_name, arguments=new_arguments)

    def _recover_missing_argument(self, tool_call: ToolCall) -> Optional[ToolCall]:
        # Never for object.delete: guessing the target of a delete removed the wrong object (a wall).
        if tool_call.tool_name not in (
            "object.transform", "object.rename",
            "material.assign", "modifier.add", "modifier.remove", "modifier.configure",
        ):
            return None

        if self._find_name_argument(tool_call) is not None:
            return None

        result = self._tool_caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        if not result.success:
            return None

        objects = result.data.get("objects", [])
        if not objects:
            return None

        names = [obj.get("name") for obj in objects if obj.get("name")]
        # Prefer an object the call already names under some other key
        # (e.g. {"object": "lamp_bulb"}); only fall back to the newest object
        # when the call names nothing at all.
        values = []
        for v in tool_call.arguments.values():
            values += [x for x in v if isinstance(x, str)] if isinstance(v, (list, tuple)) else [v]
        mentioned = [v for v in values if isinstance(v, str) and v in names]
        if mentioned:
            chosen = mentioned[0]
        elif any(isinstance(v, str) or (isinstance(v, (list, tuple)) and any(isinstance(x, str) for x in v))
                 for k, v in tool_call.arguments.items() if k not in self._valid_fields(tool_call.tool_name)):
            # The call names a target under a key we don't understand; guessing
            # "the newest object" here would edit the wrong thing.
            return None
        else:
            chosen = names[-1] if names else None
        if chosen is None:
            return None

        target_key = "old_name" if tool_call.tool_name == "object.rename" else (
            "object_name" if tool_call.tool_name in (
                "material.assign", "modifier.add", "modifier.remove", "modifier.configure",
            ) else "name"
        )

        new_arguments = dict(tool_call.arguments)
        new_arguments[target_key] = chosen
        return ToolCall(tool_name=tool_call.tool_name, arguments=new_arguments)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _valid_fields(self, tool_name: str):
        import dataclasses
        try:
            tool = self._tool_caller._registry.get(tool_name)
        except Exception:  # noqa: BLE001
            tool = None
        model = getattr(tool, "input_model", None)
        if model is None or not dataclasses.is_dataclass(model):
            return set(self.KNOWN_FIELDS)
        return {f.name for f in dataclasses.fields(model)}

    def _find_name_argument(self, tool_call: ToolCall) -> Optional[str]:
        for key in self.NAME_ARG_KEYS:
            if key in tool_call.arguments:
                return key
        return None

    def _find_similar_object_name(self, wrong_name: str) -> Optional[str]:
        result = self._tool_caller.call(ToolCall(tool_name="scene.inspect", arguments={}))
        if not result.success:
            return None

        object_names = [obj["name"] for obj in result.data.get("objects", [])]
        wrong_normalized = self._normalize(wrong_name)

        for name in object_names:
            if self._normalize(name) == wrong_normalized:
                return name

        return None

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(ch for ch in text.lower() if ch.isalnum())