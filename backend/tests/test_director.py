import asyncio

from app.config import Config
from app.director import (
    DIRECTOR_EXCERPT_CHARS,
    DIRECTOR_OPTIONS,
    DIRECTOR_WINDOW_TURNS,
    DirectorError,
    build_director_messages,
    decide_scene,
    parse_scene,
)
from app.hud import HudState
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
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


def _hud() -> HudState:
    return HudState(turn=3, location="patio", time="09:30", weather="cloudy")


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


def _decide_with_response(scenario, monkeypatch, raw, *, current_ids=None, message="entra na sala", window=None, config=None):
    async def fake_stream(self, messages, model):
        yield raw

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    return asyncio.run(
        decide_scene(
            scenario,
            _hud(),
            current_ids or [],
            message,
            window or [],
            config or _config(),
        )
    )


# --- parse_scene -----------------------------------------------------------


def test_parse_scene_happy_path(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    ids, reason = parse_scene(scenario, '{"scene": ["chloe", "renan"]}')

    assert ids == ["chloe", "renan"]
    assert reason is None


def test_parse_scene_accepts_code_fence_and_surrounding_prose(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    raw = 'Aqui está a decisão:\n```json\n{"scene": ["chloe"]}\n```\nFim.'
    ids, reason = parse_scene(scenario, raw)

    assert ids == ["chloe"]
    assert reason is None


def test_parse_scene_empty_scene_list(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    ids, reason = parse_scene(scenario, '{"scene": []}')

    assert ids == []
    assert reason is None


def test_parse_scene_prose_without_json_is_invalid(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    assert parse_scene(scenario, "a Chloe e o Renan entram") == (None, "invalid_json")


def test_parse_scene_empty_string_is_invalid(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    assert parse_scene(scenario, "") == (None, "invalid_json")


def test_parse_scene_list_root_is_invalid(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    assert parse_scene(scenario, '[{"scene": []}]') == (None, "invalid_json")


def test_parse_scene_unknown_ids(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    assert parse_scene(scenario, '{"scene": ["fantasma"]}') == (None, "unknown_ids")


def test_parse_scene_over_cap(monkeypatch, tmp_path):
    characters = {"c1.yaml": CHLOE_YAML, "c2.yaml": RENAN_YAML}
    for i in range(3, 8):
        characters[f"c{i}.yaml"] = RENAN_YAML.replace("Renan", f"Renan{i}")
    scenario = _load(monkeypatch, tmp_path, characters=characters)

    seven_ids = ["c1", "c2", "c3", "c4", "c5", "c6", "c7"]
    ids_field = ", ".join(f'"{i}"' for i in seven_ids)
    raw = f'{{"scene": [{ids_field}]}}'

    assert parse_scene(scenario, raw) == (None, "over_cap")


def test_parse_scene_not_a_list(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    assert parse_scene(scenario, '{"scene": "chloe"}') == (None, "not_a_list")


# --- build_director_messages -----------------------------------------------


def test_build_director_messages_contains_full_cast_and_scene_state(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    messages = build_director_messages(scenario, _hud(), ["chloe"], "entra na sala", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "chloe | Chloe | aluna | tier 2" in prompt_text
    assert "renan | Renan | aluno" in prompt_text
    assert "EM CENA AGORA: chloe" in prompt_text
    assert "turn=3" in prompt_text
    assert "location=patio" in prompt_text
    assert "time=09:30" in prompt_text
    assert prompt_text.strip().endswith("AÇÃO DO JOGADOR: entra na sala")


def test_build_director_messages_no_power_tier_omits_none(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    messages = build_director_messages(scenario, _hud(), [], "oi", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "renan | Renan | aluno\n" in prompt_text or prompt_text.rstrip().endswith("renan | Renan | aluno")
    assert "None" not in prompt_text


def test_build_director_messages_empty_scene_uses_none_label(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    messages = build_director_messages(scenario, _hud(), [], "oi", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "EM CENA AGORA: ninguém" in prompt_text


def test_build_director_messages_window_keeps_last_pairs_and_cuts_excerpt(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    window = []
    for i in range(10):
        window.append(ChatMessage(role="user", content=f"turno {i} jogador"))
        window.append(ChatMessage(role="assistant", content=f"turno {i} narrador"))
    window[-1] = ChatMessage(role="assistant", content="x" * 5000)

    messages = build_director_messages(scenario, _hud(), [], "oi", window)
    prompt_text = "\n".join(m.content for m in messages)

    assert "turno 0 jogador" not in prompt_text
    assert "turno 6 jogador" not in prompt_text
    assert "turno 7 jogador" in prompt_text
    assert ("x" * DIRECTOR_EXCERPT_CHARS) in prompt_text
    assert ("x" * (DIRECTOR_EXCERPT_CHARS + 1)) not in prompt_text


def test_build_director_messages_en_locale_has_no_ptbr_words(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en")

    messages = build_director_messages(scenario, _hud(), ["chloe"], "enters the room", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "EM CENA AGORA" not in prompt_text
    assert "IN SCENE NOW: chloe" in prompt_text


def test_build_director_messages_ptbr_locale_has_no_en_words(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="pt-br")

    messages = build_director_messages(scenario, _hud(), ["chloe"], "entra na sala", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "IN SCENE NOW" not in prompt_text


# --- decide_scene ------------------------------------------------------------


def test_decide_scene_happy_path_returns_ids_and_raw(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    raw = '{"scene": ["chloe", "renan"]}'

    ids, reason, returned_raw = _decide_with_response(scenario, monkeypatch, raw)

    assert ids == ["chloe", "renan"]
    assert reason is None
    assert returned_raw == raw


def test_decide_scene_accepts_wrapped_response(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    raw = 'sure, here:\n```json\n{"scene": ["chloe"]}\n```\nthanks'

    ids, reason, returned_raw = _decide_with_response(scenario, monkeypatch, raw)

    assert ids == ["chloe"]
    assert reason is None
    assert returned_raw == raw


def test_decide_scene_invalid_json(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    ids, reason, raw = _decide_with_response(scenario, monkeypatch, "")

    assert ids is None
    assert reason == "invalid_json"
    assert raw == ""


def test_decide_scene_no_utility_role_raises_without_calling_provider(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    called = []

    async def fake_stream(self, messages, model):
        called.append(True)
        yield "should not run"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    try:
        asyncio.run(
            decide_scene(scenario, _hud(), [], "oi", [], _config_without_utility())
        )
        raise AssertionError("expected DirectorError")
    except DirectorError as exc:
        assert "no utility role" in str(exc)

    assert called == []


def test_decide_scene_provider_error_becomes_director_error(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    async def fake_stream(self, messages, model):
        raise RuntimeError("boom")
        yield ""

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    try:
        asyncio.run(decide_scene(scenario, _hud(), [], "oi", [], _config()))
        raise AssertionError("expected DirectorError")
    except DirectorError:
        pass


def test_director_options_timeout_and_tokens():
    assert DIRECTOR_OPTIONS.timeout_s == 45.0
    assert DIRECTOR_OPTIONS.max_tokens == 120


def test_decide_scene_whitespace_only_response_is_invalid(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    ids, reason, raw = _decide_with_response(scenario, monkeypatch, "   ")

    assert ids is None
    assert reason == "invalid_json"
    assert raw == "   "


def test_decide_scene_builds_provider_with_director_options(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    captured = {}
    original_init = OpenAICompatProvider.__init__

    def spy_init(self, provider_config, options):
        captured["options"] = options
        original_init(self, provider_config, options)

    monkeypatch.setattr(OpenAICompatProvider, "__init__", spy_init)

    _decide_with_response(scenario, monkeypatch, '{"scene": ["chloe"]}')

    assert captured["options"] is DIRECTOR_OPTIONS


def test_build_director_messages_flattens_pipes_and_newlines_in_cast_line(monkeypatch, tmp_path):
    evil = CHLOE_YAML.replace("role: aluna", 'role: "aluna\\ndo | clube"')
    scenario = _load(monkeypatch, tmp_path, characters={"chloe.yaml": evil})

    messages = build_director_messages(scenario, _hud(), [], "oi", [])
    body = messages[1].content
    cast_line = next(line for line in body.split("\n") if line.startswith("chloe |"))

    assert cast_line == "chloe | Chloe | aluna do / clube | tier 2"
