"""
Tool (abstract base class) — Phase 2 upgrade
===============================================
Hinglish: Phase 1 mein Tool bahut simple thi — sirf name/description/execute().
Phase 2 mein hum ise "production-grade" tool contract banayenge: name,
description, input_schema (via typed input model), permission,
validate(), run(), aur structured result — jaisa spec mein bataya gaya.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generic, Optional, Type, TypeVar


class Permission(str, Enum):
    """
    Hinglish: Har tool ka ek "risk level" hoga. Future Agent (Phase 3)
    isko dekh kar decide karega — kis tool ko bina poochhe chala sakta
    hai, aur kis tool ke liye user se confirmation lena zaroori hai.
    """
    READ_ONLY = "read_only"       # scene.inspect — kuch modify nahi karta
    SAFE_WRITE = "safe_write"     # object.create — reversible, low risk
    DESTRUCTIVE = "destructive"   # object.delete — data loss ho sakta hai
    PYTHON_EXECUTION = "python_execution"

@dataclass
class ToolResult:
    """
    Hinglish: Har tool ka result is EXACT same shape mein aayega —
    random dict nahi. Isse Agent/UI/tests ko pata rehta hai result
    kaise parse karna hai, chahe tool koi bhi ho (Consistency).
    """
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @staticmethod
    def ok(data: Dict[str, Any] = None) -> "ToolResult":
        return ToolResult(success=True, data=data or {})

    @staticmethod
    def fail(error: str) -> "ToolResult":
        return ToolResult(success=False, error=error)


TInput = TypeVar("TInput")


class Tool(ABC, Generic[TInput]):
    """
    Hinglish: Har concrete tool isko extend karega.

    Generic[TInput]: har Tool subclass apna khud ka typed input model
    bata sakta hai (jaise Phase 2.4 mein CreateObjectInput). Abhi
    read-only tools (scene.inspect) ke liye input_model None rahega.
    """

    name: str = ""
    description: str = ""
    permission: Permission = Permission.SAFE_WRITE
    input_model: Optional[Type[Any]] = None  # dataclass jo input define karega

    def validate(self, input_data: Dict[str, Any]) -> TInput:
        """
        Hinglish: Raw dict ko typed input object mein convert karta hai.

        Agar input_model set nahi hai (jaise scene.inspect), toh raw
        dict hi wapas kar dete hain — backward compatible.

        Agar input_model set hai, dataclass construct karte waqt:
          - Missing/extra fields -> TypeError -> humara ValueError
          - __post_init__ ke andar wale checks -> ValueError seedha propagate
        Dono cases mein caller (execute()) ko clean ValueError milta hai.

        PATCHED (robustness): Chhote/fast LLMs (jaise openai/gpt-oss-20b)
        kabhi-kabhi tool ke exact field names follow nahi karte — jaise
        `object.create` ke liye `primitive` ki jagah `type` bhej dete
        hain. Isse pehle seedha TypeError crash hota tha. Ab yahan pehle
        arguments ko dataclass ke asli field names ke saath normalize
        karte hain: known aliases map karte hain, aur jo bhi key kisi
        bhi field se match nahi hoti wo silently drop kar dete hain
        (crash karne ki jagah) — taaki weaker model ka minor schema
        mismatch poore task ko fail na kare.
        """
        if self.input_model is None:
            return input_data  # type: ignore

        normalized_input = self._normalize_input(input_data or {})

        try:
            return self.input_model(**normalized_input)
        except TypeError as exc:
            raise ValueError(f"Invalid input for tool '{self.name}': {exc}") from exc
        except ValueError:
            raise  # __post_init__ ka apna ValueError hai, waisa hi propagate karo

    # ---------------------------------------------------------
    # Common aliases models mistakenly use instead of the real field name.
    # Only applied when the real field name doesn't already have a value.
    # ---------------------------------------------------------
    _FIELD_ALIASES = {
        "type": ("primitive", "object_type"),
        "shape": ("primitive",),
        "kind": ("primitive",),
        "object_name": ("name",),
        "position": ("location",),
    }

    def _normalize_input(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        import dataclasses

        if not dataclasses.is_dataclass(self.input_model):
            return input_data

        valid_fields = {f.name for f in dataclasses.fields(self.input_model)}
        normalized: Dict[str, Any] = {}

        for key, value in input_data.items():
            if key in valid_fields:
                normalized[key] = value
                continue

            aliases = self._FIELD_ALIASES.get(key, ())
            target = next((a for a in aliases if a in valid_fields and a not in normalized), None)
            if target is not None:
                normalized[target] = value
            # Hinglish: agar koi alias bhi nahi milta, is unknown key ko
            # chhod dete hain — dataclass constructor ko crash nahi karne
            # dete ek anjaani key ke liye.

        return normalized

    @abstractmethod
    def run(self, validated_input: TInput) -> ToolResult:
        """
        Hinglish: Asli tool logic yahan likhna hai. Har subclass isko
        implement karega. Ye validate() ke BAAD call hota hai — isliye
        andar already-validated, typed input milta hai.
        """
        raise NotImplementedError

    def execute(self, input_data: Dict[str, Any] = None) -> ToolResult:
        """
        Hinglish: TEMPLATE METHOD PATTERN.

        Public entry point (`execute`) ka flow FIXED hai:
            validate() -> run() -> errors ko ToolResult.fail() mein catch karo

        Har subclass sirf `run()` implement karta hai — validation aur
        error-handling baar-baar likhne ki zaroorat nahi, wo yahin
        base class mein ek hi jagah handle ho gaya (DRY principle).
        """
        try:
            validated = self.validate(input_data or {})
        except ValueError as exc:
            return ToolResult.fail(str(exc))

        try:
            return self.run(validated)
        except Exception as exc:  # deliberately broad — ek tool crash se poora addon na gire
            return ToolResult.fail(f"Tool '{self.name}' failed: {exc}")