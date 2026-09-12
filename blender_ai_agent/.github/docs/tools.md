# Writing a Tool

Every Blender capability the agent can use is a `Tool` (`blender_ai_agent/tools/base.py`). The agent never touches `bpy` directly — it only calls tools by name through the `ToolRegistry`.

## The contract

```python
from dataclasses import dataclass
from blender_ai_agent.tools.base import Permission, Tool, ToolResult

@dataclass
class MyToolInput:
    name: str

    def __post_init__(self):
        if not self.name:
            raise ValueError("MyToolInput.name must not be empty")

class MyTool(Tool):
    name = "category.action"
    description = "One sentence describing what this does."
    permission = Permission.SAFE_WRITE
    input_model = MyToolInput

    def __init__(self, bridge):
        self._bridge = bridge

    def run(self, validated_input: MyToolInput) -> ToolResult:
        # ... call self._bridge, never bpy directly ...
        return ToolResult.ok({"name": validated_input.name})
```

`execute()` is provided by the base class (Template Method pattern) — it validates input, calls your `run()`, and catches any exception into a failed `ToolResult`. You never override `execute()`.

## Using the SDK shortcut

For simple tools, `sdk/tools.py`'s `create_tool()` avoids writing the dataclass and class by hand — see its docstring for an example.

## Registering

Add your tool to `_register_tools()` in the root `__init__.py`.

## Testing

Use `tests/fakes.py`'s `FakeBridge` — no real Blender required. See any `tests/test_*_tools.py` file for the pattern.