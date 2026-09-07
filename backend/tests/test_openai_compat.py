import json

import httpx
import pytest
from pydantic import ValidationError

from app.config import ProviderConfig
from app.llm.base import ChatMessage, EmbeddingOptions, GenerationOptions
from app.llm import openai_compat
from app.llm.openai_compat import (
    SYSTEM_FOLD_ACK,
    SYSTEM_INSTRUCTIONS_TAG,
    EmbedError,
    OpenAICompatProvider,
    ProviderAuthError,
)


def _provider(system_mode: str = "system", options: GenerationOptions | None = None) -> OpenAICompatProvider:
    config = ProviderConfig(base_url="http://x/v1", system_mode=system_mode)
    return OpenAICompatProvider(config, options)


def test_fold_into_user_wraps_system_and_inserts_ack():
    provider = _provider("fold_into_user")
    messages = [
        ChatMessage(role="system", content="master prompt"),
        ChatMessage(role="user", content="Sento no degrau."),
    ]

    payload = provider.build_payload(messages, "m")

    assert payload["messages"] == [
        {
            "role": "user",
            "content": f"<{SYSTEM_INSTRUCTIONS_TAG}>\nmaster prompt\n</{SYSTEM_INSTRUCTIONS_TAG}>",
        },
        {"role": "assistant", "content": SYSTEM_FOLD_ACK},
        {"role": "user", "content": "Sento no degrau."},
    ]


def test_default_mode_does_not_transform_messages():
    provider = _provider("system")
    messages = [
        ChatMessage(role="system", content="master prompt"),
        ChatMessage(role="user", content="hi"),
    ]

    payload = provider.build_payload(messages, "m")

    assert payload["messages"] == [
        {"role": "system", "content": "master prompt"},
        {"role": "user", "content": "hi"},
    ]


def test_fold_into_user_joins_multiple_system_messages_and_keeps_user_order():
    provider = _provider("fold_into_user")
    messages = [
        ChatMessage(role="system", content="first"),
        ChatMessage(role="system", content="second"),
        ChatMessage(role="user", content="one"),
        ChatMessage(role="user", content="two"),
    ]

    payload = provider.build_payload(messages, "m")

    assert payload["messages"][0] == {
        "role": "user",
        "content": f"<{SYSTEM_INSTRUCTIONS_TAG}>\nfirst\nsecond\n</{SYSTEM_INSTRUCTIONS_TAG}>",
    }
    assert payload["messages"][1] == {"role": "assistant", "content": SYSTEM_FOLD_ACK}
    assert payload["messages"][2] == {"role": "user", "content": "one"}
    assert payload["messages"][3] == {"role": "user", "content": "two"}


def test_no_system_message_leaves_list_unchanged_in_both_modes():
    messages = [ChatMessage(role="user", content="hi")]

    for mode in ("system", "fold_into_user"):
        provider = _provider(mode)
        payload = provider.build_payload(messages, "m")
        assert payload["messages"] == [{"role": "user", "content": "hi"}]


def test_response_format_and_max_tokens_present_in_both_modes():
    options = GenerationOptions(max_tokens=42, json_schema={"type": "object"}, schema_name="s")
    messages = [
        ChatMessage(role="system", content="prompt"),
        ChatMessage(role="user", content="hi"),
    ]

    for mode in ("system", "fold_into_user"):
        config = ProviderConfig(base_url="http://x/v1", system_mode=mode, structured_output="json_schema")
        provider = OpenAICompatProvider(config, options)
        payload = provider.build_payload(messages, "m")
        assert payload["max_tokens"] == 42
        assert payload["response_format"] == {
            "type": "json_schema",
            "json_schema": {"name": "s", "schema": {"type": "object"}, "strict": True},
        }


def test_reasoning_effort_present_when_set():
    options = GenerationOptions(reasoning_effort="low")
    provider = _provider(options=options)
    messages = [ChatMessage(role="user", content="hi")]

    payload = provider.build_payload(messages, "m")

    assert payload["reasoning_effort"] == "low"


def test_reasoning_effort_absent_when_unset():
    provider = _provider()
    messages = [ChatMessage(role="user", content="hi")]

    payload = provider.build_payload(messages, "m")

    assert "reasoning_effort" not in payload


def test_reasoning_effort_coexists_with_other_options():
    options = GenerationOptions(
        max_tokens=42,
        temperature=0.3,
        json_schema={"type": "object"},
        schema_name="s",
        reasoning_effort="low",
    )
    config = ProviderConfig(base_url="http://x/v1", system_mode="system", structured_output="json_schema")
    provider = OpenAICompatProvider(config, options)
    messages = [ChatMessage(role="user", content="hi")]

    payload = provider.build_payload(messages, "m")

    assert payload["max_tokens"] == 42
    assert payload["temperature"] == 0.3
    assert payload["reasoning_effort"] == "low"
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "s", "schema": {"type": "object"}, "strict": True},
    }


def test_reasoning_effort_none_is_validation_error():
    with pytest.raises(ValidationError):
        GenerationOptions(reasoning_effort="none")


def test_supports_temperature_false_omits_temperature_key():
    config = ProviderConfig(base_url="http://x/v1", supports_temperature=False)
    options = GenerationOptions(temperature=0.7)
    provider = OpenAICompatProvider(config, options)
    messages = [ChatMessage(role="user", content="hi")]

    payload = provider.build_payload(messages, "m")

    assert "temperature" not in payload


def test_supports_temperature_false_keeps_other_fields():
    config = ProviderConfig(base_url="http://x/v1", supports_temperature=False, structured_output="json_schema")
    options = GenerationOptions(
        temperature=0.7,
        max_tokens=42,
        json_schema={"type": "object"},
        schema_name="s",
    )
    provider = OpenAICompatProvider(config, options)
    messages = [ChatMessage(role="user", content="hi")]

    payload = provider.build_payload(messages, "m")

    assert "temperature" not in payload
    assert payload["max_tokens"] == 42
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "s", "schema": {"type": "object"}, "strict": True},
    }


def test_supports_temperature_true_keeps_temperature_key():
    config = ProviderConfig(base_url="http://x/v1", supports_temperature=True)
    options = GenerationOptions(temperature=0.7)
    provider = OpenAICompatProvider(config, options)
    messages = [ChatMessage(role="user", content="hi")]

    payload = provider.build_payload(messages, "m")

    assert payload["temperature"] == 0.7


def test_supports_temperature_false_without_temperature_option_is_fine():
    config = ProviderConfig(base_url="http://x/v1", supports_temperature=False)
    provider = OpenAICompatProvider(config)
    messages = [ChatMessage(role="user", content="hi")]

    payload = provider.build_payload(messages, "m")

    assert "temperature" not in payload


def _mock_provider(monkeypatch, handler, embedding_options: EmbeddingOptions | None = None) -> OpenAICompatProvider:
    transport = httpx.MockTransport(handler)

    class _TransportClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.llm.openai_compat.httpx.AsyncClient", _TransportClient)
    config = ProviderConfig(base_url="http://x/v1", api_key_env="OPENROUTER_API_KEY")
    return OpenAICompatProvider(config, embedding_options=embedding_options)


def _embed_response(vectors: list[list[float]]) -> httpx.Response:
    return httpx.Response(200, json={"data": [{"embedding": v} for v in vectors]})


@pytest.mark.asyncio
async def test_embed_two_texts_one_batch_preserves_order(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert json.loads(request.content) == {
            "model": "m",
            "input": ["a", "b"],
            "encoding_format": "float",
        }
        return _embed_response([[1.0, 2.0], [3.0, 4.0]])

    provider = _mock_provider(monkeypatch, handler)

    vectors = await provider.embed(["a", "b"], "m")

    assert len(calls) == 1
    assert str(calls[0].url) == "http://x/v1/embeddings"
    assert vectors == [[1.0, 2.0], [3.0, 4.0]]


@pytest.mark.asyncio
async def test_embed_batch_size_one_makes_three_requests(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return _embed_response([[float(len(calls))]])

    provider = _mock_provider(monkeypatch, handler, EmbeddingOptions(batch_size=1))

    vectors = await provider.embed(["a", "b", "c"], "m")

    assert len(calls) == 3
    assert vectors == [[1.0], [2.0], [3.0]]


@pytest.mark.asyncio
async def test_embed_empty_list_makes_no_request(monkeypatch):
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return _embed_response([])

    provider = _mock_provider(monkeypatch, handler)

    vectors = await provider.embed([], "m")

    assert vectors == []
    assert called is False


@pytest.mark.asyncio
async def test_embed_reorders_vectors_by_response_index(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [3.0, 4.0], "index": 1},
                    {"embedding": [1.0, 2.0], "index": 0},
                ]
            },
        )

    provider = _mock_provider(monkeypatch, handler)

    vectors = await provider.embed(["a", "b"], "m")

    assert vectors == [[1.0, 2.0], [3.0, 4.0]]


@pytest.mark.asyncio
async def test_embed_sends_encoding_format_float(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return _embed_response([[1.0]])

    provider = _mock_provider(monkeypatch, handler)

    await provider.embed(["a"], "m")

    assert captured["payload"]["encoding_format"] == "float"


@pytest.mark.asyncio
async def test_embed_item_not_a_dict_raises_embed_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": ["not-a-dict"]})

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(EmbedError):
        await provider.embed(["a"], "m")


@pytest.mark.asyncio
async def test_embed_embedding_wrong_type_raises_embed_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"embedding": "base64-blob"}]})

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(EmbedError):
        await provider.embed(["a"], "m")


@pytest.mark.asyncio
async def test_embed_batch_count_mismatch_raises_before_totals_line_up(monkeypatch):
    """Batch A over-returns and batch B under-returns by the same amount: the
    total across batches matches len(texts), so only the per-batch check catches it."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return _embed_response([[1.0], [2.0]])
        return _embed_response([])

    provider = _mock_provider(monkeypatch, handler, EmbeddingOptions(batch_size=1))

    with pytest.raises(EmbedError):
        await provider.embed(["a", "b"], "m")


@pytest.mark.asyncio
async def test_embed_non_json_body_raises_embed_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json", headers={"content-type": "text/plain"})

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(EmbedError):
        await provider.embed(["a"], "m")


@pytest.mark.asyncio
async def test_embed_without_credential_env_set_still_sends_request(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer none"
        return _embed_response([[1.0]])

    provider = _mock_provider(monkeypatch, handler)

    vectors = await provider.embed(["a"], "m")

    assert vectors == [[1.0]]


@pytest.mark.asyncio
async def test_embed_call_event_emitted_on_success(monkeypatch):
    events = []
    monkeypatch.setattr(openai_compat, "emit", lambda event, **props: events.append((event, props)))

    def handler(request: httpx.Request) -> httpx.Response:
        return _embed_response([[1.0, 2.0], [3.0, 4.0]])

    provider = _mock_provider(monkeypatch, handler)

    await provider.embed(["a", "b"], "m")

    assert len(events) == 1
    name, props = events[0]
    assert name == "embed_call"
    assert props["model"] == "m"
    assert props["texts"] == 2
    assert props["batches"] == 1
    assert props["dim"] == 2
    assert isinstance(props["duration_ms"], int)
    assert props["error"] is None
    assert "?" not in props["provider"]


@pytest.mark.asyncio
async def test_embed_call_event_emitted_on_failure(monkeypatch):
    events = []
    monkeypatch.setattr(openai_compat, "emit", lambda event, **props: events.append((event, props)))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(EmbedError):
        await provider.embed(["a"], "m")

    assert len(events) == 1
    name, props = events[0]
    assert name == "embed_call"
    assert props["error"] is not None
    assert props["dim"] is None


@pytest.mark.asyncio
async def test_embed_vectors_with_different_dimensions_pass_through(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return _embed_response([[1.0, 2.0], [3.0]])

    provider = _mock_provider(monkeypatch, handler)

    vectors = await provider.embed(["a", "b"], "m")

    assert vectors == [[1.0, 2.0], [3.0]]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_embed_rejected_credential_raises_provider_auth_error(monkeypatch, status):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text="denied")

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(ProviderAuthError, match=r"\$OPENROUTER_API_KEY"):
        await provider.embed(["a"], "m")


@pytest.mark.asyncio
async def test_embed_server_error_raises_embed_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(EmbedError):
        await provider.embed(["a"], "m")


@pytest.mark.asyncio
async def test_embed_missing_data_key_raises_embed_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"nope": True})

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(EmbedError):
        await provider.embed(["a"], "m")


@pytest.mark.asyncio
async def test_embed_vector_count_mismatch_raises_embed_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return _embed_response([[1.0, 2.0]])

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(EmbedError):
        await provider.embed(["a", "b"], "m")


@pytest.mark.asyncio
async def test_embed_timeout_raises_embed_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    provider = _mock_provider(monkeypatch, handler)

    with pytest.raises(EmbedError):
        await provider.embed(["a"], "m")


@pytest.mark.asyncio
async def test_embed_timeout_option_reaches_httpx_timeout(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        return _embed_response([[1.0]])

    transport = httpx.MockTransport(handler)

    class _TransportClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.llm.openai_compat.httpx.AsyncClient", _TransportClient)
    config = ProviderConfig(base_url="http://x/v1")
    provider = OpenAICompatProvider(config, embedding_options=EmbeddingOptions(timeout_s=7.5))

    await provider.embed(["a"], "m")

    timeout = captured["timeout"]
    assert timeout.read == 7.5
    assert timeout.connect == 10.0
