from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Literal

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
    reasoning_effort: Literal["low", "medium", "high"] | None = None


class EmbeddingOptions(BaseModel):
    timeout_s: float = 60.0
    batch_size: int = 32


class LLMProvider(ABC):
    @abstractmethod
    def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        """Yield text deltas for a chat completion."""

    async def complete(self, messages: list[ChatMessage], model: str) -> str:
        """Non-streamed call, built on top of stream_chat."""
        parts = [delta async for delta in self.stream_chat(messages, model)]
        return "".join(parts)

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        """Vectors in the same order as texts. Raises EmbedError."""
        raise NotImplementedError
