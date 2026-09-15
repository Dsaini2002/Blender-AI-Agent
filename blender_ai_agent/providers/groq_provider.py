"""
GroqProvider — Real LLM Provider (Free tier, high throughput)
===================================================================
Hinglish: GeminiProvider jaisa hi ModelProvider implementation, bas
Groq ke OpenAI-compatible Chat Completions endpoint ke saath.

Zaroori: koi extra pip package install NAHI karni — Python ki
built-in `urllib` se hi REST call ho jaati hai. Isse Blender ke
internal Python mein `pip install` ka jhanjhat nahi (jaisa Gemini
ke liye `google-generativeai` install karna pada tha).

Groq free tier: 30 requests/minute, ~1000/day per model — Gemini ke
20/day se kaafi zyada. Free models: openai/gpt-oss-120b,
openai/gpt-oss-20b, qwen/qwen3-32b (sab function-calling support
karte hain).
"""

import json
import urllib.error
import urllib.request

from .base import ModelProvider
from ..agent.models import ModelResponse, ToolCall, Usage


class GroqProvider(ModelProvider):

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key: str, model_name: str = "openai/gpt-oss-120b"):
        self._api_key = api_key
        self._model_name = model_name

    def generate(self, request) -> ModelResponse:
        payload = {
            "model": self._model_name,
            "messages": self._build_messages(request.messages),
        }

        tools = self._build_tools(request.tools)
        if tools:
            payload["tools"] = tools

        body = self._call_api(payload)
        return self._parse_response(body)

    # ---------------------------------------------------------
    # Private helpers
    # ---------------------------------------------------------
    def _call_api(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
                # Hinglish: Groq Cloudflare ke peeche hai — urllib ka
                # default User-Agent ("Python-urllib/3.x") bot jaisa
                # lagta hai aur 403/error 1010 de deta hai. Normal
                # browser-jaisa User-Agent dene se ye block nahi hota.
                "User-Agent": "Mozilla/5.0 (compatible; BlenderAIAgent/1.0)",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Groq API error {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Groq API request failed: {exc.reason}") from exc

    def _build_messages(self, messages):
        """
        Hinglish: Humara Message list -> OpenAI-compatible 'messages' array.

        Zaroori: tumhara `Message` dataclass abhi `tool_call_id` track
        nahi karta, jo OpenAI-compatible APIs (Groq) ko `role: "tool"`
        messages ke liye zaroori hota hai (assistant ke tool_calls[].id
        se match karne ke liye). Jab tak wo proper threading add na ho,
        "tool" role ko "user" mein collapse karte hain — bilkul wahi
        tareeka jo GeminiProvider._build_contents() already use karta
        hai. Isse strict validation error nahi aata.
        """
        built = []
        for msg in messages:
            role = msg.role
            content = msg.content
            if role == "tool":
                role = "user"
                content = f"[Tool result] {content}"
            built.append({"role": role, "content": content})
        return built

    def _build_tools(self, tool_definitions):
        if not tool_definitions:
            return []

        return [
            {
                "type": "function",
                "function": {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "parameters": tool_def.parameters or {"type": "object", "properties": {}},
                },
            }
            for tool_def in tool_definitions
        ]

    def _parse_response(self, body: dict) -> ModelResponse:
        try:
            choice = body["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Groq response shape: {body}") from exc

        tool_calls = []
        for tc in message.get("tool_calls") or []:
            func = tc.get("function", {})
            raw_arguments = func.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}
            tool_calls.append(ToolCall(tool_name=func.get("name", ""), arguments=arguments))

        content = message.get("content")

        usage_data = body.get("usage", {})
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
        )

        return ModelResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            usage=usage,
        )