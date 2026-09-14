"""
GeminiProvider — Real LLM Provider
=======================================
Hinglish: Phase 3 ka ModelProvider abstraction implement karta hai
Google Gemini ke saath. Isse Agent ko koi fark nahi padta — same
interface jo MockProvider follow karta hai.
"""

import json

from .base import ModelProvider
from ..agent.models import ModelResponse, ToolCall, Usage


class GeminiProvider(ModelProvider):

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._genai = genai
        self._model_name = model_name

    def generate(self, request) -> ModelResponse:
        tools = self._build_tools(request.tools)

        model = self._genai.GenerativeModel(
            model_name=self._model_name,
            tools=tools if tools else None,
        )

        contents = self._build_contents(request.messages)
        response = model.generate_content(contents)

        return self._parse_response(response)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _build_tools(self, tool_definitions):
        if not tool_definitions:
            return []

        function_declarations = []
        for tool_def in tool_definitions:
            function_declarations.append({
                "name": tool_def.name,
                "description": tool_def.description,
                "parameters": tool_def.parameters or {"type": "object", "properties": {}},
            })

        return [{"function_declarations": function_declarations}]

    def _build_contents(self, messages):
        """Hinglish: Humare Message list ko Gemini ke 'contents' format mein badalta hai."""
        contents = []
        for msg in messages:
            role = "model" if msg.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": msg.content}]})
        return contents

    def _parse_response(self, response) -> ModelResponse:
        tool_calls = []
        text_content = None

        try:
            candidate = response.candidates[0]
            for part in candidate.content.parts:
                if hasattr(part, "function_call") and part.function_call and part.function_call.name:
                    fc = part.function_call
                    arguments = dict(fc.args) if fc.args else {}
                    tool_calls.append(ToolCall(tool_name=fc.name, arguments=arguments))
                elif hasattr(part, "text") and part.text:
                    text_content = part.text
        except (IndexError, AttributeError):
            text_content = getattr(response, "text", "") or "I couldn't generate a response."

        usage = Usage()
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = Usage(
                prompt_tokens=getattr(response.usage_metadata, "prompt_token_count", 0),
                completion_tokens=getattr(response.usage_metadata, "candidates_token_count", 0),
            )

        return ModelResponse(
            content=text_content,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=usage,
        )