import json
from collections.abc import AsyncIterator

import httpx

from app.config import ProviderConfig
from app.llm.base import ChatMessage, GenerationOptions, LLMProvider


class OpenAICompatProvider(LLMProvider):
    def __init__(self, provider: ProviderConfig, options: GenerationOptions | None = None):
        self.base_url = provider.base_url.rstrip("/")
        self.api_key = provider.api_key
        self.options = options or GenerationOptions()

    def build_payload(self, messages: list[ChatMessage], model: str) -> dict:
        payload: dict = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        }
        if self.options.max_tokens is not None:
            payload["max_tokens"] = self.options.max_tokens
        if self.options.temperature is not None:
            payload["temperature"] = self.options.temperature
        return payload

    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        payload = self.build_payload(messages, model)
        headers = {"Authorization": f"Bearer {self.api_key}"}
        timeout = httpx.Timeout(self.options.timeout_s, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions", json=payload, headers=headers
            ) as response:
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
