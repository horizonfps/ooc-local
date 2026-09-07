import json
from collections.abc import AsyncIterator

import httpx

from app.config import ProviderConfig
from app.llm.base import ChatMessage, GenerationOptions, LLMProvider


class ProviderAuthError(RuntimeError):
    """Missing or rejected API key, distinct from a transport failure."""


SYSTEM_INSTRUCTIONS_TAG = "system-instructions"
SYSTEM_FOLD_ACK = "Understood."


def _fold_system_into_user(messages: list[ChatMessage]) -> list[ChatMessage]:
    system = [m for m in messages if m.role == "system"]
    if not system:
        return messages
    text = "\n".join(m.content for m in system)
    wrapped = f"<{SYSTEM_INSTRUCTIONS_TAG}>\n{text}\n</{SYSTEM_INSTRUCTIONS_TAG}>"
    rest = [m for m in messages if m.role != "system"]
    return [
        ChatMessage(role="user", content=wrapped),
        ChatMessage(role="assistant", content=SYSTEM_FOLD_ACK),
        *rest,
    ]


class OpenAICompatProvider(LLMProvider):
    def __init__(self, provider: ProviderConfig, options: GenerationOptions | None = None):
        self.base_url = provider.base_url.rstrip("/")
        self.api_key = provider.api_key
        self.api_key_env = provider.api_key_env
        self.structured_output = provider.structured_output
        self.system_mode = provider.system_mode
        self.options = options or GenerationOptions()

    def build_payload(self, messages: list[ChatMessage], model: str) -> dict:
        if self.system_mode == "fold_into_user":
            messages = _fold_system_into_user(messages)
        payload: dict = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        }
        if self.options.max_tokens is not None:
            payload["max_tokens"] = self.options.max_tokens
        if self.options.temperature is not None:
            payload["temperature"] = self.options.temperature
        if self.structured_output == "json_schema" and self.options.json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": self.options.schema_name,
                    "schema": self.options.json_schema,
                    "strict": True,
                },
            }
        return payload

    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        payload = self.build_payload(messages, model)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        timeout = httpx.Timeout(self.options.timeout_s, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
            ) as response:
                if response.status_code in (401, 403):
                    raise ProviderAuthError(
                        f"provider rejected the credential from ${self.api_key_env}"
                    )
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    delta = (
                        json.loads(data).get("choices", [{}])[0].get("delta", {}).get("content")
                    )
                    if delta:
                        yield delta
