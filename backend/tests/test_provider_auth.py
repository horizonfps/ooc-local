import httpx
import pytest

from app.config import ProviderConfig
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider, ProviderAuthError

MESSAGES = [ChatMessage(role="user", content="hi")]


def _provider(monkeypatch, status: int) -> OpenAICompatProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="denied")

    transport = httpx.MockTransport(handler)
    original = httpx.AsyncClient.__init__

    def patched(self, *args, **kwargs):
        kwargs["transport"] = transport
        original(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched)
    config = ProviderConfig(base_url="http://x/v1", api_key_env="OPENROUTER_API_KEY")
    return OpenAICompatProvider(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_rejected_credential_names_the_env_var(monkeypatch, status):
    provider = _provider(monkeypatch, status)
    with pytest.raises(ProviderAuthError, match=r"\$OPENROUTER_API_KEY"):
        async for _ in provider.stream_chat(MESSAGES, "m"):
            pass


@pytest.mark.asyncio
async def test_other_http_errors_stay_http_status_errors(monkeypatch):
    provider = _provider(monkeypatch, 500)
    with pytest.raises(httpx.HTTPStatusError):
        async for _ in provider.stream_chat(MESSAGES, "m"):
            pass
