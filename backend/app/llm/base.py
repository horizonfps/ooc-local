from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class GenerationOptions(BaseModel):
    max_tokens: int | None = None
    temperature: float | None = None
    timeout_s: float = 120.0
    json_schema: dict | None = None
    schema_name: str = "response"


class LLMProvider(ABC):
    @abstractmethod
    def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        """Yield text deltas for a chat completion."""

    async def complete(self, messages: list[ChatMessage], model: str) -> str:
        """Non-streamed call, built on top of stream_chat."""
        parts = [delta async for delta in self.stream_chat(messages, model)]
        return "".join(parts)
