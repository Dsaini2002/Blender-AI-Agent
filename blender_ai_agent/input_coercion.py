"""
input_coercion.py
==================
Hinglish: LLM (khaaskar chhote/free models) tool arguments ko kabhi bilkul sahi type mein nahi bhejte:

    "location": "1, 2, 3"            (list ki jagah string)
    "color": ["0.3", "0.4", "0.5"]   (numbers ki jagah strings)
    "width": 640.0 / "640"           (int ki jagah float/string)
    "location": {"x": 1, "y": 2, "z": 3}
    proto lists/dicts (Gemini SDK)   (asli list/dict nahi)

Pehle har tool ke input model mein alag-alag patch lagane padte the aur har naye tool par wahi galti
dobara aati thi. Ye module EK jagah (har tool ke dataclass ke type-hints dekhkar) arguments ko sahi type mein
badal deta hai. Rules:
  - kabhi exception nahi uthata — kuch samajh na aaye to value jaisi hai waisi chhod deta hai
    (phir tool ka apna validation saaf error deta hai)
  - sirf type-hint ke hisaab se badalta hai; str/dict/Any fields ko nahi chhedta
  - sirf standard library
"""

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
    """Gemini ke proto list/dict -> asli Python list/dict (recursive). Plain data par koi asar nahi."""
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
    """value ko list banane ki koshish (string / x-y-z dict / tuple). Na ban sake to None."""
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        text = value.strip()
        if element_type is str:
            return [value]                               # List[str] ko ek string mila -> [string]
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


def coerce_value(value: Any, annotation: Any) -> Any:
    """Ek value ko type-hint ke hisaab se badalta hai. Kabhi exception nahi."""
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
        if tp in (list, tuple) or origin in (list, tuple, typing.Sequence):
            args = get_args(tp)
            element = args[0] if args else Any
            sequence = _as_sequence(value, element)
            if sequence is None:
                return value
            if element is Any:
                return sequence
            return [coerce_value(item, element) for item in sequence]

        return value
    except Exception:  # noqa: BLE001 — coercion kabhi task ko fail na kare
        return value


def coerce_arguments(input_model: Any, arguments: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Tool ke `input_model` (dataclass) ke type-hints dekhkar `arguments` ke har field ko sahi type mein badalta hai.
    Dataclass na ho / hints na milein to bas proto-containers ko plain karta hai. Original dict ko nahi chhedta.
    """
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