from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class LLMProvider(ABC):
    @abstractmethod
    def stream_chat(self, messages: list[ChatMessage], model: str) -> AsyncIterator[str]:
        """Yield text deltas for a chat completion."""
