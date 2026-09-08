"""
ToolRegistry
============
Hinglish: Saare tools yahan register hote hain aur naam se retrieve
kiye ja sakte hain.
"""

from typing import Dict, List

from .base import Tool


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if not tool.name:
            raise ValueError("Tool must have a non-empty 'name'.")
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' already registered.")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry.")
        return self._tools[name]

    def list_tools(self) -> List[str]:
        return list(self._tools.keys())