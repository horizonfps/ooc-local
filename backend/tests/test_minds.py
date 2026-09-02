import asyncio

import pytest

from app.cast import MindView
from app.config import Config
from app.llm.openai_compat import OpenAICompatProvider
from app.minds import (
    EMOJI_CHARS,
    MIND_FIELD_CHARS,
    MIND_SHEET_CHARS,
    MINDS_NARRATOR_CHARS,
    MINDS_OPTIONS,
    MindRejection,
    MindsError,
    build_minds_messages,
    merge_minds,
    parse_minds,
    think_minds,
)
from app.scenario import load_scenario

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
appearance: baixa, cabelo curto
personality: extrovertida
voice: animada
power_tier: 2
mind:
  feeling: curiosa
  goal: descobrir segredo
"""

RENAN_YAML = """\
name: Renan
role: aluno
appearance: alto
personality: quieto
voice: baixa
mind:
  feeling: cansado
  goal: passar despercebido
"""

CHARACTERS = {"chloe.yaml": CHLOE_YAML, "renan.yaml": RENAN_YAML}


def _write_scenario(root, scenario_id="exemplo-escola", *, locale="pt-br", characters=None):
    scenario_yaml = SCENARIO_YAML_PTBR if locale == "pt-br" else SCENARIO_YAML_EN
    characters = characters if characters is not None else CHARACTERS

    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    for filename, content in characters.items():
        (characters_dir / filename).write_text(content, encoding="utf-8")

    return scenario_path


def _load(monkeypatch, tmp_path, *, locale="pt-br", characters=None):
    _write_scenario(tmp_path, locale=locale, characters=characters)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return load_scenario("exemplo-escola")


def _config():
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"utility": {"provider": "local", "model": "m"}},
        }
    )


def _config_without_utility():
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
        }
    )


def _think_with_response(scenario, monkeypatch, raw, *, cast_ids=None, previous=None, message="entra na sala", narrator_text="ela sorri", config=None):
    async def fake_stream(self, messages, model):
        yield raw

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    return asyncio.run(
        think_minds(
            scenario,
            cast_ids or ["chloe", "renan"],
            previous or {},
            message,
            narrator_text,
            config or _config(),
        )
    )


CAST_IDS = ["chloe", "renan"]


# --- parse_minds -------------------------------------------------------------


def test_parse_minds_happy_path():
    raw = '{"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}'

    data, reason = parse_minds(raw)

    assert data == {"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}
    assert reason is None


def test_parse_minds_accepts_code_fence_and_surrounding_prose():
    raw = (
        "Aqui está:\n```json\n"
        '{"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}'
        "\n```\nFim."
    )

    data, reason = parse_minds(raw)

    assert data == {"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}
    assert reason is None


def test_parse_minds_empty_object():
    assert parse_minds("{}") == ({}, None)


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "a Chloe ficou desconfiada", '{"chloe": {', '[{"chloe": {}}]'],
)
def test_parse_minds_malformed_is_invalid_json(raw):
    assert parse_minds(raw) == (None, "invalid_json")


def test_parse_minds_duplicate_key_last_one_wins():
    raw = (
        '{"chloe": {"attitude": "A", "emoji": "🙂", "event": "A"}, '
        '"chloe": {"attitude": "B", "emoji": "😠", "event": "B"}}'
    )

    data, reason = parse_minds(raw)

    assert data == {"chloe": {"attitude": "B", "emoji": "😠", "event": "B"}}
    assert reason is None


# --- merge_minds ---------------------------------------------------------------


def test_merge_minds_happy_path_no_previous():
    proposed = {"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}

    entries, rejections = merge_minds({}, proposed, CAST_IDS)

    assert entries == {"chloe": MindView(attitude="curiosa", emoji="🙂", event="te viu")}
    assert rejections == []


def test_merge_minds_returns_full_map_not_delta():
    previous = {"renan": MindView(attitude="cansado", emoji="😪", event="bocejou")}
    proposed = {"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}

    entries, rejections = merge_minds(previous, proposed, CAST_IDS)

    assert entries["chloe"] == MindView(attitude="curiosa", emoji="🙂", event="te viu")
    assert entries["renan"] == previous["renan"]
    assert rejections == []


def test_merge_minds_proposal_out_of_cast_ids_keeps_previous_entry():
    previous = {"renan": MindView(attitude="cansado", emoji="😪", event="bocejou")}
    proposed = {"renan": {"attitude": "novo", "emoji": "😀", "event": "novo evento"}}

    entries, rejections = merge_minds(previous, proposed, ["chloe"])

    assert entries["renan"] == previous["renan"]
    assert rejections == [MindRejection(id="renan", reason="not_in_scene")]


def test_merge_minds_clamps_attitude_length():
    proposed = {"chloe": {"attitude": "x" * 500, "emoji": "🙂", "event": "te viu"}}

    entries, _ = merge_minds({}, proposed, CAST_IDS)

    assert len(entries["chloe"].attitude) == MIND_FIELD_CHARS


def test_merge_minds_clamps_emoji_to_code_points():
    proposed = {"chloe": {"attitude": "a", "emoji": "🤨🤨🤨🤨🤨", "event": "b"}}

    entries, _ = merge_minds({}, proposed, CAST_IDS)

    assert entries["chloe"].emoji == "🤨🤨🤨🤨"
    assert len(entries["chloe"].emoji) == EMOJI_CHARS


def test_merge_minds_emoji_clamp_drops_trailing_zwj():
    proposed = {"chloe": {"attitude": "a", "emoji": "👨‍👩‍👧", "event": "b"}}

    entries, _ = merge_minds({}, proposed, CAST_IDS)

    assert not entries["chloe"].emoji.endswith("‍")


def test_merge_minds_missing_field_falls_back_to_previous_then_empty():
    previous = {"chloe": MindView(attitude="curiosa", emoji="🙂", event="te viu")}
    proposed = {"chloe": {"attitude": "desconfiada", "emoji": "🤨"}}

    entries, _ = merge_minds(previous, proposed, CAST_IDS)
    assert entries["chloe"].event == "te viu"

    entries_no_previous, _ = merge_minds({}, proposed, CAST_IDS)
    assert entries_no_previous["chloe"].event == ""


@pytest.mark.parametrize(
    "proposed,rejected_id,reason",
    [
        ({"chloe": {"attitude": 7, "emoji": [], "event": None}}, "chloe", "empty"),
        ({"Chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}, "Chloe", "not_in_scene"),
        ({"chloe": "desconfiada"}, "chloe", "invalid_shape"),
    ],
)
def test_merge_minds_named_rejections(proposed, rejected_id, reason):
    entries, rejections = merge_minds({}, proposed, CAST_IDS)

    assert rejected_id not in entries
    assert rejections == [MindRejection(id=rejected_id, reason=reason)]


def test_merge_minds_not_a_map():
    previous = {"renan": MindView(attitude="cansado", emoji="😪", event="bocejou")}

    entries, rejections = merge_minds(previous, [], CAST_IDS)

    assert entries == previous
    assert entries is not previous
    assert rejections == [MindRejection(id="", reason="not_a_map")]


def test_merge_minds_empty_proposal_equals_previous_and_no_rejections():
    previous = {"renan": MindView(attitude="cansado", emoji="😪", event="bocejou")}

    entries, rejections = merge_minds(previous, {}, CAST_IDS)

    assert entries == previous
    assert rejections == []


def test_merge_minds_does_not_mutate_previous():
    previous = {"renan": MindView(attitude="cansado", emoji="😪", event="bocejou")}
    previous_copy = dict(previous)
    proposed = {"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}

    merge_minds(previous, proposed, CAST_IDS)

    assert previous == previous_copy


# --- build_minds_messages -----------------------------------------------------


def test_build_minds_messages_has_body_with_action_and_narration(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    messages = build_minds_messages(scenario, CAST_IDS, {}, "entra na sala", "ela sorri")
    prompt_text = "\n".join(m.content for m in messages)

    assert "chloe | Chloe |" in prompt_text
    assert "renan | Renan |" in prompt_text
    assert "AÇÃO DO JOGADOR: entra na sala" in prompt_text
    assert "ela sorri" in prompt_text


def test_build_minds_messages_includes_current_mind_only_for_known_previous(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    previous = {"chloe": MindView(attitude="desconfiada", emoji="🤨", event="viu voce mentir")}

    messages = build_minds_messages(scenario, CAST_IDS, previous, "oi", "narracao")
    body = messages[1].content
    chloe_line = next(line for line in body.split("\n") if line.startswith("chloe |"))
    renan_line = next(line for line in body.split("\n") if line.startswith("renan |"))

    assert "agora: 🤨 desconfiada" in chloe_line
    assert "agora:" not in renan_line


def test_build_minds_messages_skips_unknown_cast_id(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    messages = build_minds_messages(scenario, ["chloe", "fantasma"], {}, "oi", "narracao")
    prompt_text = "\n".join(m.content for m in messages)

    assert "fantasma" not in prompt_text


def test_build_minds_messages_cuts_narrator_text(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    narrator_text = "x" * 5000

    messages = build_minds_messages(scenario, CAST_IDS, {}, "oi", narrator_text)
    prompt_text = "\n".join(m.content for m in messages)

    assert ("x" * MINDS_NARRATOR_CHARS) in prompt_text
    assert ("x" * (MINDS_NARRATOR_CHARS + 1)) not in prompt_text


def test_build_minds_messages_sheet_is_cut_hard_at_mind_sheet_chars(monkeypatch, tmp_path):
    long_personality = "y" * 300
    evil_chloe = CHLOE_YAML.replace("personality: extrovertida", f"personality: {long_personality}")
    scenario = _load(monkeypatch, tmp_path, characters={"chloe.yaml": evil_chloe, "renan.yaml": RENAN_YAML})

    messages = build_minds_messages(scenario, ["chloe"], {}, "oi", "narracao")
    line = messages[1].content.split("\n")[1]

    assert line.startswith("chloe | Chloe | aluna | ")
    sheet = line[len("chloe | Chloe | ") :]
    assert len(sheet) == MIND_SHEET_CHARS


def test_build_minds_messages_en_locale_has_no_ptbr_words(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en")

    messages = build_minds_messages(scenario, CAST_IDS, {}, "enters the room", "she smiles")
    prompt_text = "\n".join(m.content for m in messages)

    assert "NPCS EM CENA" not in prompt_text
    assert "NPCS IN SCENE" in prompt_text


def test_build_minds_messages_ptbr_locale_has_no_en_words(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="pt-br")

    messages = build_minds_messages(scenario, CAST_IDS, {}, "entra na sala", "ela sorri")
    prompt_text = "\n".join(m.content for m in messages)

    assert "NPCS IN SCENE" not in prompt_text


# --- think_minds ---------------------------------------------------------------


def test_think_minds_happy_path_returns_proposal_and_raw(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    raw = '{"chloe": {"attitude": "desconfiada", "emoji": "🤨", "event": "viu voce pegar o caderno"}}'

    proposed, reason, returned_raw = _think_with_response(scenario, monkeypatch, raw)

    assert proposed == {
        "chloe": {"attitude": "desconfiada", "emoji": "🤨", "event": "viu voce pegar o caderno"}
    }
    assert reason is None
    assert returned_raw == raw


def test_think_minds_builds_provider_with_minds_options(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    captured = {}
    original_init = OpenAICompatProvider.__init__

    def spy_init(self, provider_config, options):
        captured["options"] = options
        original_init(self, provider_config, options)

    monkeypatch.setattr(OpenAICompatProvider, "__init__", spy_init)

    _think_with_response(scenario, monkeypatch, '{"chloe": {"attitude": "a", "emoji": "🙂", "event": "b"}}')

    assert captured["options"] is MINDS_OPTIONS


def test_think_minds_no_utility_role_raises_without_calling_provider(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    called = []

    async def fake_stream(self, messages, model):
        called.append(True)
        yield "should not run"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(MindsError, match="no utility role"):
        asyncio.run(
            think_minds(scenario, CAST_IDS, {}, "oi", "narracao", _config_without_utility())
        )

    assert called == []


def test_think_minds_provider_error_becomes_minds_error(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    async def fake_stream(self, messages, model):
        raise RuntimeError("boom")
        yield ""

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(MindsError):
        asyncio.run(think_minds(scenario, CAST_IDS, {}, "oi", "narracao", _config()))


def test_think_minds_whitespace_only_response_is_invalid(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    proposed, reason, raw = _think_with_response(scenario, monkeypatch, "   ")

    assert proposed is None
    assert reason == "invalid_json"
    assert raw == "   "


def test_minds_options_timeout_and_tokens():
    assert MINDS_OPTIONS.max_tokens == 300
    assert MINDS_OPTIONS.timeout_s == 45.0
