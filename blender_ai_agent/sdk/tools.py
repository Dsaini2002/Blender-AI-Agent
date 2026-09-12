"""
Tool SDK — Step 10.5
=========================
Hinglish: Third-party developers ke liye boilerplate kam karta hai.
Bina SDK ke, ek naya tool banane ke liye developer ko Tool class,
dataclass input model, __post_init__ validation — sab manually
likhna padta. SDK ye pattern automate karta hai.
"""

from dataclasses import make_dataclass, field as dataclass_field
from typing import Any, Callable, Dict, Type

from ..tools.base import Permission, Tool, ToolResult


def create_tool(
    name: str,
    description: str,
    permission: Permission,
    fields: Dict[str, Any],
    run_fn: Callable[[Any, Any], ToolResult],
) -> Type[Tool]:
    """
    Hinglish: Developer isko call karke, bina manually Tool subclass
    likhe, ek naya tool bana sakta hai.

    `fields` — dataclass fields dict, jaise {"name": str, "count": int}
    `run_fn` — signature: run_fn(self, validated_input) -> ToolResult

    Example:
        MyTool = create_tool(
            name="product.create_stand",
            description="Creates a display stand.",
            permission=Permission.SAFE_WRITE,
            fields={"height": float},
            run_fn=lambda self, inp: ToolResult.ok({"height": inp.height}),
        )
    """
    input_model = make_dataclass(
        f"{name.replace('.', '_')}_Input",
        [(field_name, field_type) for field_name, field_type in fields.items()],
    )

    tool_class = type(
        f"{name.replace('.', '_')}_Tool",
        (Tool,),
        {
            "name": name,
            "description": description,
            "permission": permission,
            "input_model": input_model,
            "__init__": lambda self, bridge=None: setattr(self, "_bridge", bridge),
            "run": run_fn,
        },
    )

    return tool_class