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
        Hinglish: Raw dict (jo future mein LLM/UI se aayega) ko typed
        input object mein convert karta hai.

        Agar input_model set nahi hai (jaise scene.inspect), toh raw
        dict hi wapas kar dete hain — backward compatible.

        Zaroori fields missing hone par ValueError — "fail fast,
        fail clear" principle.
        """
        if self.input_model is None:
            return input_data  # type: ignore

        try:
            return self.input_model(**(input_data or {}))
        except TypeError as exc:
            raise ValueError(f"Invalid input for tool '{self.name}': {exc}") from exc

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