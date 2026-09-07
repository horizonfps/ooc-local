import json
import time
from collections.abc import AsyncIterator

import httpx

from app.config import ProviderConfig
from app.llm.base import ChatMessage, EmbeddingOptions, GenerationOptions, LLMProvider
from app.observability import emit


class ProviderAuthError(RuntimeError):
    """Missing or rejected API key, distinct from a transport failure."""


class EmbedError(RuntimeError):
    """Embedding request failed or came back in an unusable shape."""


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
    def __init__(
        self,
        provider: ProviderConfig,
        options: GenerationOptions | None = None,
        embedding_options: EmbeddingOptions | None = None,
    ):
        self.base_url = provider.base_url.rstrip("/")
        self.api_key = provider.api_key
        self.api_key_env = provider.api_key_env
        self.structured_output = provider.structured_output
        self.system_mode = provider.system_mode
        self.supports_temperature = provider.supports_temperature
        self.options = options or GenerationOptions()
        self.embedding_options = embedding_options or EmbeddingOptions()

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
        if self.options.temperature is not None and self.supports_temperature:
            payload["temperature"] = self.options.temperature
        if self.options.reasoning_effort is not None:
            payload["reasoning_effort"] = self.options.reasoning_effort
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

    async def embed(self, texts: list[str], model: str) -> list[list[float]]:
        if not texts:
            return []
        start = time.monotonic()
        error: str | None = None
        vectors: list[list[float]] = []
        try:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            timeout = httpx.Timeout(self.embedding_options.timeout_s, connect=10.0)
            batch_size = self.embedding_options.batch_size
            async with httpx.AsyncClient(timeout=timeout) as client:
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
                    vectors.extend(await self._embed_batch(client, headers, batch, model))
            if len(vectors) != len(texts):
                raise EmbedError(
                    f"expected {len(texts)} vectors, got {len(vectors)}"
                )
            return vectors
        except ProviderAuthError:
            error = "auth"
            raise
        except EmbedError as exc:
            error = str(exc)
            raise
        except httpx.HTTPError as exc:
            error = str(exc)
            raise EmbedError(f"embedding request failed: {exc}") from exc
        finally:
            emit(
                "embed_call",
                provider=self.base_url,
                model=model,
                texts=len(texts),
                batches=(len(texts) + self.embedding_options.batch_size - 1)
                // self.embedding_options.batch_size
                if texts
                else 0,
                dim=len(vectors[0]) if vectors else None,
                duration_ms=int((time.monotonic() - start) * 1000),
                error=error,
            )

    async def _embed_batch(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        batch: list[str],
        model: str,
    ) -> list[list[float]]:
        payload = {"model": model, "input": batch}
        response = await client.post(f"{self.base_url}/embeddings", json=payload, headers=headers)
        if response.status_code in (401, 403):
            raise ProviderAuthError(
                f"provider rejected the credential from ${self.api_key_env}"
            )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EmbedError(f"embedding request failed with status {response.status_code}") from exc
        try:
            body = response.json()
        except ValueError as exc:
            raise EmbedError("embedding response body is not valid JSON") from exc
        data = body.get("data")
        if not isinstance(data, list):
            raise EmbedError("embedding response is missing 'data'")
        vectors: list[list[float]] = []
        for item in data:
            embedding = item.get("embedding") if isinstance(item, dict) else None
            if embedding is None:
                raise EmbedError("embedding response item is missing 'embedding'")
            vectors.append(embedding)
        if len(vectors) != len(batch):
            raise EmbedError(
                f"expected {len(batch)} vectors in batch, got {len(vectors)}"
            )
        return vectors
