import pytest
from pydantic import ValidationError

from app.config import ProviderConfig, load_config
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import OpenAICompatProvider

MESSAGES = [ChatMessage(role="user", content="hi")]
SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string"}}}


def test_json_schema_provider_with_schema_emits_response_format():
    provider = ProviderConfig(base_url="http://x/v1", structured_output="json_schema")
    options = GenerationOptions(json_schema=SCHEMA, schema_name="judgement")
    payload = OpenAICompatProvider(provider, options).build_payload(MESSAGES, "m")
    assert payload["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "judgement", "schema": SCHEMA, "strict": True},
    }


def test_response_format_coexists_with_existing_keys():
    provider = ProviderConfig(base_url="http://x/v1", structured_output="json_schema")
    options = GenerationOptions(json_schema=SCHEMA)
    payload = OpenAICompatProvider(provider, options).build_payload(MESSAGES, "m")
    assert payload["model"] == "m"
    assert payload["messages"] == [m.model_dump() for m in MESSAGES]
    assert payload["stream"] is True
    assert "response_format" in payload


def test_default_structured_output_omits_response_format_even_with_schema():
    provider = ProviderConfig(base_url="http://x/v1")
    options = GenerationOptions(json_schema=SCHEMA)
    payload = OpenAICompatProvider(provider, options).build_payload(MESSAGES, "m")
    assert "response_format" not in payload


def test_json_schema_provider_without_schema_omits_response_format():
    provider = ProviderConfig(base_url="http://x/v1", structured_output="json_schema")
    options = GenerationOptions()
    payload = OpenAICompatProvider(provider, options).build_payload(MESSAGES, "m")
    assert "response_format" not in payload


def test_max_tokens_temperature_and_schema_coexist():
    provider = ProviderConfig(base_url="http://x/v1", structured_output="json_schema")
    options = GenerationOptions(max_tokens=10, temperature=0.5, json_schema=SCHEMA)
    payload = OpenAICompatProvider(provider, options).build_payload(MESSAGES, "m")
    assert payload["max_tokens"] == 10
    assert payload["temperature"] == 0.5
    assert "response_format" in payload


def test_generation_options_defaults_have_no_schema():
    options = GenerationOptions()
    assert options.json_schema is None
    assert options.schema_name == "response"


def test_provider_config_rejects_unknown_structured_output():
    with pytest.raises(ValidationError):
        ProviderConfig(base_url="http://x/v1", structured_output="gbnf")


def test_load_config_resolves_structured_output_per_provider(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  local: {base_url: http://x/v1, structured_output: json_schema}\n"
        "  other: {base_url: http://y/v1}\n"
        "models:\n"
        "  narrator: {provider: local, model: m}\n"
        "  utility:  {provider: other, model: m}\n"
        "  builder:  {provider: local, model: m}\n",
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.providers["local"].structured_output == "json_schema"
    assert config.providers["other"].structured_output == "none"
