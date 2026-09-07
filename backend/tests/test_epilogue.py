import asyncio

import pytest

from app.config import Config
from app.epilogue import (
    ENDING_OPTIONS,
    EPILOGUE_EXCERPT_CHARS,
    EPILOGUE_WINDOW_TURNS,
    MILESTONE_OPTIONS,
    EpilogueError,
    build_ending_messages,
    build_milestone_messages,
    write_ending,
    write_milestone,
)
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import AchievementDef, load_scenario

WORLD_MD = "# Mundo\n\nUma escola nas montanhas.\n"

SCENARIO_YAML_PTBR = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

SCENARIO_YAML_EN = """\
name: Example School
tagline: a tagline
locale: en
"""

DEFAULT_START = """\
name: Começo
prologue: prologo
opening_scene: Você acorda no dormitório.
hud:
  location: dormitorio
  time: "08:00"
  weather: clear
"""

CHLOE_YAML = """\
name: Chloe
role: aluna
appearance: baixa
personality: extrovertida
voice: animada
mind:
  feeling: curiosa
  goal: descobrir segredo
"""


def _write_scenario(root, scenario_id="exemplo-escola", *, locale="pt-br"):
    scenario_yaml = SCENARIO_YAML_PTBR if locale == "pt-br" else SCENARIO_YAML_EN

    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    return scenario_path


def _load(monkeypatch, tmp_path, *, locale="pt-br", scenario_id="exemplo-escola"):
    _write_scenario(tmp_path, scenario_id=scenario_id, locale=locale)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return load_scenario(scenario_id)


def _achievement(**overrides) -> AchievementDef:
    data = {
        "id": "found-secret",
        "name": "Achou o segredo",
        "type": "achievement",
        "condition": "Descobriu o segredo da Chloe",
    }
    data.update(overrides)
    return AchievementDef.model_validate(data)


def _config(structured_output="none"):
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1", "structured_output": structured_output}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
        }
    )


def _config_without_narrator():
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"utility": {"provider": "local", "model": "m"}},
        }
    )


def _window(n: int) -> list[ChatMessage]:
    return [ChatMessage(role="user" if i % 2 == 0 else "assistant", content=f"turno {i}") for i in range(n)]


def _parts(messages: list[ChatMessage]) -> tuple[str, str]:
    return messages[0].content, messages[1].content


# --- build_milestone_messages -----------------------------------------------


def test_build_milestone_messages_happy_path(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement()

    messages = build_milestone_messages(scenario, achievement, _window(4))
    system, body = messages[0].content, messages[1].content

    assert "narrador" in system
    assert "Achou o segredo" in body
    assert "Descobriu o segredo da Chloe" in body
    assert "turno 0" in body and "turno 3" in body


def test_build_milestone_messages_excludes_hint(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement(hint="não conte isso ao jogador")

    _, body = _parts(build_milestone_messages(scenario, achievement, _window(2)))

    assert "não conte isso ao jogador" not in body


def test_build_milestone_messages_field_collapses_whitespace_and_pipe(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement(condition="linha um\nlinha dois | terceira")

    _, body = _parts(build_milestone_messages(scenario, achievement, _window(2)))

    assert "\n" not in body.split("\n")[0]
    assert "linha um linha dois / terceira" in body


# --- build_ending_messages ---------------------------------------------------


def test_build_ending_messages_with_compact_has_summary_block(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement(id="final-feliz", type="ending", name="Final feliz", condition="Chegou ao fim")

    _, body = _parts(build_ending_messages(scenario, achievement, _window(2), "resumo anterior aqui"))

    assert "RESUMO ANTERIOR" in body
    assert "resumo anterior aqui" in body


@pytest.mark.parametrize("compact", [None, ""])
def test_build_ending_messages_without_compact_has_no_summary_block(monkeypatch, tmp_path, compact):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement(id="final-feliz", type="ending", name="Final feliz", condition="Chegou ao fim")

    _, body = _parts(build_ending_messages(scenario, achievement, _window(2), compact))

    assert "RESUMO ANTERIOR" not in body


def test_build_ending_messages_window_truncated_to_most_recent(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement(id="final-feliz", type="ending", name="Final feliz", condition="Chegou ao fim")

    window = _window(40)
    _, body = _parts(build_ending_messages(scenario, achievement, window, None))

    expected_count = EPILOGUE_WINDOW_TURNS * 2
    assert f"turno {40 - expected_count}" in body
    assert "turno 39" in body
    assert "turno 0" not in body


def test_build_ending_messages_message_truncated_per_excerpt_chars(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement(id="final-feliz", type="ending", name="Final feliz", condition="Chegou ao fim")

    giant = ChatMessage(role="user", content="x" * (EPILOGUE_EXCERPT_CHARS * 2))
    _, body = _parts(build_ending_messages(scenario, achievement, [giant], None))

    assert "x" * EPILOGUE_EXCERPT_CHARS in body
    assert "x" * (EPILOGUE_EXCERPT_CHARS + 1) not in body


def test_build_messages_locale_en(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en")
    achievement = _achievement()

    system, _ = _parts(build_milestone_messages(scenario, achievement, _window(2)))

    assert "narrator of this story" in system


def test_build_messages_unknown_locale_falls_back_to_ptbr(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    scenario = scenario.model_copy(update={"meta": scenario.meta.model_copy(update={"locale": "pt-br"})})
    achievement = _achievement()

    system, _ = _parts(build_milestone_messages(scenario, achievement, _window(2)))

    assert "narrador" in system


# --- options / no schema -----------------------------------------------------


def test_options_have_no_json_schema():
    assert MILESTONE_OPTIONS.json_schema is None
    assert ENDING_OPTIONS.json_schema is None


def test_build_payload_has_no_response_format_even_with_structured_provider(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement()
    messages = build_milestone_messages(scenario, achievement, _window(2))

    config = _config(structured_output="json_schema")
    provider = OpenAICompatProvider(config.providers["local"], MILESTONE_OPTIONS)
    payload = provider.build_payload(messages, "m")

    assert "response_format" not in payload


# --- write_milestone / write_ending ------------------------------------------


def _run_with_response(coro_factory, monkeypatch, raw):
    async def fake_stream(self, messages, model):
        yield raw

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    return asyncio.run(coro_factory())


def test_write_milestone_strips_surrounding_whitespace(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement()

    text = _run_with_response(
        lambda: write_milestone(scenario, achievement, _window(2), _config()),
        monkeypatch,
        "  o texto do marco  ",
    )

    assert text == "o texto do marco"


def test_write_milestone_uses_narrator_provider_and_options(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement()

    captured = {}
    original_init = OpenAICompatProvider.__init__

    def spy_init(self, provider, options=None):
        captured["options"] = options
        original_init(self, provider, options)

    monkeypatch.setattr(OpenAICompatProvider, "__init__", spy_init)

    _run_with_response(
        lambda: write_milestone(scenario, achievement, _window(2), _config()),
        monkeypatch,
        "texto",
    )

    assert captured["options"] is MILESTONE_OPTIONS


def test_write_ending_uses_ending_options(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement(id="final-feliz", type="ending", name="Final feliz", condition="Chegou ao fim")

    captured = {}
    original_init = OpenAICompatProvider.__init__

    def spy_init(self, provider, options=None):
        captured["options"] = options
        original_init(self, provider, options)

    monkeypatch.setattr(OpenAICompatProvider, "__init__", spy_init)

    _run_with_response(
        lambda: write_ending(scenario, achievement, _window(2), None, _config()),
        monkeypatch,
        "epilogo",
    )

    assert captured["options"] is ENDING_OPTIONS


def test_write_ending_keeps_engine_tag_intact(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement(id="final-feliz", type="ending", name="Final feliz", condition="Chegou ao fim")

    text = _run_with_response(
        lambda: write_ending(scenario, achievement, _window(2), None, _config()),
        monkeypatch,
        "o fim chegou [LOC:patio]",
    )

    assert text == "o fim chegou [LOC:patio]"


@pytest.mark.parametrize("raw", ["   ", ""])
def test_write_milestone_empty_response_raises(monkeypatch, tmp_path, raw):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement()

    with pytest.raises(EpilogueError):
        _run_with_response(
            lambda: write_milestone(scenario, achievement, _window(2), _config()),
            monkeypatch,
            raw,
        )


def test_write_milestone_provider_error_becomes_epilogue_error(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement()

    async def fake_stream(self, messages, model):
        raise RuntimeError("boom")
        yield ""

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(EpilogueError, match="boom"):
        asyncio.run(write_milestone(scenario, achievement, _window(2), _config()))


def test_write_milestone_without_narrator_role_raises_before_network(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    achievement = _achievement()

    def fail_init(self, *args, **kwargs):
        raise AssertionError("provider must not be constructed")

    monkeypatch.setattr(OpenAICompatProvider, "__init__", fail_init)

    with pytest.raises(EpilogueError, match="no narrator role"):
        asyncio.run(write_milestone(scenario, achievement, _window(2), _config_without_narrator()))


def test_epilogue_options_do_not_request_reasoning_effort():
    assert MILESTONE_OPTIONS.reasoning_effort is None
    assert ENDING_OPTIONS.reasoning_effort is None
