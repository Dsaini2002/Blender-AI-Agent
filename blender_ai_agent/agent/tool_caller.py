"""
ToolCaller — Step 3.4
========================
Hinglish: Ye class ToolRegistry aur LLM ke beech ka "translator" hai.

Direction 1: Registry ke tools ko ToolDefinition list mein convert
karta hai (LLM ko batane ke liye kya-kya available hai).

Direction 2: LLM ka ToolCall leke, sahi tool dhoondke, execute karta
hai, aur ToolResult wapas deta hai.

Important: LLM ko kabhi bhi raw Tool object nahi milta — sirf naam
aur description. Actual execution hamesha ToolRegistry ke through
hota hai.
"""

from typing import List

from ..agent.models import ToolCall, ToolDefinition
from ..tools.base import ToolResult


class ToolCaller:

    def __init__(self, registry):
        # Dependency Injection — jaisa hamesha karte hain
        self._registry = registry

    def get_tool_definitions(self) -> List[ToolDefinition]:
        """
        Hinglish: Registry ke saare tools ko LLM-readable format mein
        convert karta hai. Ye Agent LLM ko request bhejte waqt use
        karega (ModelRequest.tools).
        """
        definitions = []
        for tool_name in self._registry.list_tools():
            tool = self._registry.get(tool_name)
            definitions.append(ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=self._build_parameters_schema(tool),
            ))
        return definitions

    def call(self, tool_call: ToolCall) -> ToolResult:
        """
        Hinglish: LLM ne jo tool call maanga hai, usse actually
        execute karta hai. Agar tool exist hi nahi karta, ToolResult
        ke andar hi error return hota hai — crash nahi hota. Ye
        important hai kyunki LLM kabhi galat/hallucinated tool name
        bhi bol sakta hai.
        """
        try:
            tool = self._registry.get(tool_call.tool_name)
        except KeyError:
            return ToolResult.fail(f"Unknown tool: '{tool_call.tool_name}'")

        return tool.execute(tool_call.arguments)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _build_parameters_schema(self, tool) -> dict:
        """
        Hinglish: Tool ke input_model (dataclass) se ek simple schema
        banata hai — field names ki list. Real OpenAI/Anthropic format
        (JSON Schema) Step baad mein refine karenge jab real provider
        add karenge; abhi ke liye simple aur kaam-chalau version.
        """
        if tool.input_model is None:
            return {}

        try:
            field_names = list(tool.input_model.__dataclass_fields__.keys())
        except AttributeError:
            return {}

        return {"fields": field_names}