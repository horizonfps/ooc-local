import pytest
from pydantic import ValidationError

from app.config import ProviderConfig
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import (
    SYSTEM_FOLD_ACK,
    SYSTEM_INSTRUCTIONS_TAG,
    OpenAICompatProvider,
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
