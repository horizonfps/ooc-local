import json
from collections.abc import AsyncIterator

import httpx

from app.config import ProviderConfig
from app.llm.base import ChatMessage, LLMProvider


class OpenAICompatProvider(LLMProvider):
    def __init__(self, provider: ProviderConfig):
        self.base_url = provider.base_url.rstrip("/")
        self.api_key = provider.api_key

    async def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        payload = {
            "model": model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
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
