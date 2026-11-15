"""input_coercion.py"""

import dataclasses
import re
import typing
from typing import Any, Dict, Optional, Union, get_args, get_origin

try:  # Python 3.10+: `X | None`
    from types import UnionType  # type: ignore
except ImportError:  # pragma: no cover
    UnionType = None

_TRUE = {"true", "yes", "y", "1", "on"}
_FALSE = {"false", "no", "n", "0", "off"}
_NUMBER = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?|-?\.\d+", re.IGNORECASE)


def to_plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, bytes, bool, int, float)):
        return value
    if isinstance(value, dict) or (hasattr(value, "items") and callable(value.items)):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)) or hasattr(value, "__iter__"):
        return [to_plain(v) for v in value]
    return value


def _unwrap_optional(tp: Any) -> Any:
    origin = get_origin(tp)
    if origin is Union or (UnionType is not None and origin is UnionType):
        members = [a for a in get_args(tp) if a is not type(None)]
        if len(members) == 1:
            return members[0]
    return tp


def _to_float(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return value
    return value


def _to_int(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    number = _to_float(value)
    if isinstance(number, (int, float)) and not isinstance(number, bool) and float(number).is_integer():
        return int(number)
    return value


def _to_bool(value: Any) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE:
            return True
        if lowered in _FALSE:
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return value


def _as_sequence(value: Any, element_type: Any) -> Optional[list]:
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if element_type is str:
            return [value]
        text = text.strip("[]()")
        numbers = _NUMBER.findall(text)
        parts = [p for p in re.split(r"[,;\s]+", text) if p]
        if parts and len(numbers) == len(parts):
            return parts                                  # "1, 2, 3" / "1 2 3" / "(1,2,3)"
        return None
    if isinstance(value, dict):
        lowered = {str(k).lower(): v for k, v in value.items()}
        for keys in (("x", "y", "z"), ("r", "g", "b"), ("red", "green", "blue")):
            if all(k in lowered for k in keys):
                seq = [lowered[k] for k in keys]
                for extra in ("w", "a", "alpha"):
                    if extra in lowered and len(keys) == 3 and keys != ("x", "y", "z"):
                        seq.append(lowered[extra])
                        break
                return seq
    return None


def _json_value(value: Any) -> Any:
    """A string that holds JSON ('{"a": 1}' or '[1, 2]') -> the parsed value; anything else unchanged."""
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("{", "[") and text[-1:] in ("}", "]"):
            try:
                import json
                return json.loads(text)
            except ValueError:
                return value
    return value


def coerce_value(value: Any, annotation: Any) -> Any:
    try:
        tp = _unwrap_optional(annotation)
        if value is None:
            return None
        value = to_plain(value)

        if tp is bool:
            return _to_bool(value)
        if tp is int:
            return _to_int(value)
        if tp is float:
            return _to_float(value)
        if tp is str:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return str(value)
            return value

        origin = get_origin(tp)
        if tp is dict or origin is dict:
            parsed = _json_value(value)
            return parsed if isinstance(parsed, dict) else value
        if tp is Any:
            return _json_value(value)
        if tp in (list, tuple) or origin in (list, tuple, typing.Sequence):
            args = get_args(tp)
            element = args[0] if args else Any
            parsed = _json_value(value) if isinstance(value, str) and value.strip().startswith("[") else value
            sequence = list(parsed) if isinstance(parsed, (list, tuple)) else _as_sequence(value, element)
            if sequence is None:
                return value
            if element is Any:
                return sequence
            return [coerce_value(item, element) for item in sequence]

        return value
    except Exception:  # noqa: BLE001 
        return value


def coerce_arguments(input_model: Any, arguments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    plain = to_plain(arguments) if arguments else {}
    if not isinstance(plain, dict):
        return plain
    if input_model is None or not dataclasses.is_dataclass(input_model):
        return plain

    try:
        hints = typing.get_type_hints(input_model)
    except Exception:  # noqa: BLE001
        return plain

    return {key: (coerce_value(value, hints[key]) if key in hints else value) for key, value in plain.items()}