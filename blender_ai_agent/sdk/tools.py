"""Tool SDK"""

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
    """`fields`
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