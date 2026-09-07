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
