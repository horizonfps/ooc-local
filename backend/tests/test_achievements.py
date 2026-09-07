import asyncio

import pytest

from app.achievements import (
    ACHIEVEMENT_EXCERPT_CHARS,
    ACHIEVEMENTS_OPTIONS,
    MAX_CANDIDATES_PER_CALL,
    AchievementError,
    AchievementsResponse,
    apply_verdicts,
    build_achievement_messages,
    eligible,
    judge_achievements,
    parse_achievements,
)
from app.config import Config
from app.hud import DynamicStat, HudState
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import AchievementDef, StatGate, load_scenario

WORLD_MD = "# Mundo\n\nUma escola nas montanhas.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: {locale}
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
mind:
  feeling: curiosa
  goal: descobrir segredo
"""

STATS_YAML = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 50
"""


def _write_scenario(root, scenario_id="exemplo-escola", *, locale="pt-br"):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML.format(locale=locale), encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")
    (scenario_path / "stats.yaml").write_text(STATS_YAML, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    return scenario_path


def _load(monkeypatch, tmp_path, *, locale="pt-br"):
    _write_scenario(tmp_path, locale=locale)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return load_scenario("exemplo-escola")


def _hud(**overrides) -> HudState:
    base = dict(turn=3, location="patio", time="09:30", weather="cloudy", stats={"reputacao": 50})
    base.update(overrides)
    return HudState(**base)


def _config(structured_output="none"):
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1", "structured_output": structured_output}},
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


def _achievement(id="ach-1", type="achievement", condition="fez algo", min_turn=None, stat_gates=None):
    return AchievementDef(
        id=id,
        name="Nome",
        type=type,
        condition=condition,
        min_turn=min_turn,
        stat_gates=stat_gates or [],
    )


def _judge_with_response(scenario, candidates, monkeypatch, raw, *, message="ameaça a aluna", narrator_text="ela recua", window=None, config=None):
    async def fake_stream(self, messages, model):
        yield raw

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    return asyncio.run(
        judge_achievements(
            scenario,
            candidates,
            message,
            narrator_text,
            window or [],
            config or _config(),
        )
    )


# --- eligible -------------------------------------------------------------------


def test_eligible_filters_unlocked_min_turn_and_free():
    unlocked = _achievement(id="already-done")
    barred = _achievement(id="barred", min_turn=10)
    free = _achievement(id="free")

    result = eligible([unlocked, barred, free], _hud(turn=3), unlocked_ids=["already-done"])

    assert [a.id for a in result] == ["free"]


def test_eligible_min_turn_exactly_equal_is_candidate():
    achievement = _achievement(min_turn=5)
    assert eligible([achievement], _hud(turn=4), []) == []
    assert eligible([achievement], _hud(turn=5), []) == [achievement]


def test_eligible_stat_gate_exactly_equal_is_candidate():
    achievement = _achievement(stat_gates=[StatGate(id="reputacao", at_least=60)])
    assert eligible([achievement], _hud(stats={"reputacao": 59}), []) == []
    assert eligible([achievement], _hud(stats={"reputacao": 60}), []) == [achievement]


def test_eligible_dynamic_stat_gate_uses_dynamic_value():
    achievement = _achievement(stat_gates=[StatGate(id="confianca", at_least=5)])
    hud = _hud(dynamic_stats={"confianca": DynamicStat(name="Confiança", value=5, max=10)})
    assert eligible([achievement], hud, []) == [achievement]


def test_eligible_gate_on_missing_id_rejects_candidate():
    achievement = _achievement(stat_gates=[StatGate(id="inexistente", at_least=1)])
    assert eligible([achievement], _hud(), []) == []


def test_eligible_two_gates_both_must_pass():
    achievement = _achievement(
        stat_gates=[StatGate(id="reputacao", at_least=60), StatGate(id="outro", at_least=1)]
    )
    assert eligible([achievement], _hud(stats={"reputacao": 100}), []) == []


def test_eligible_does_not_apply_max_candidates_cap():
    achievements = [_achievement(id=f"ach-{i}") for i in range(12)]
    assert len(eligible(achievements, _hud(), [])) == 12


def test_eligible_empty_list_returns_empty():
    assert eligible([], _hud(), []) == []


# --- build_achievement_messages --------------------------------------------------


def test_build_achievement_messages_lists_candidates_and_action(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    candidates = [_achievement(id="ach-1", type="achievement", condition="fez algo bom")]

    messages = build_achievement_messages(scenario, candidates, "entra na sala", "ok", [])
    body = messages[1].content

    assert "ach-1 | achievement | fez algo bom" in body
    assert "entra na sala" in body


def test_build_achievement_messages_collapses_pipe_and_newline_in_condition(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    candidates = [_achievement(id="ach-1", condition="fez\nisso | aquilo")]

    messages = build_achievement_messages(scenario, candidates, "ação", "ok", [])
    body = messages[1].content

    assert "ach-1 | achievement | fez isso / aquilo" in body
    lines = body.splitlines()
    matching = [line for line in lines if line.startswith("ach-1")]
    assert len(matching) == 1


def test_build_achievement_messages_caps_at_max_candidates(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    candidates = [_achievement(id=f"ach-{i}") for i in range(12)]

    messages = build_achievement_messages(scenario, candidates, "ação", "ok", [])
    body = messages[1].content

    assert body.count("| achievement |") == MAX_CANDIDATES_PER_CALL
    assert "ach-8" not in body


def test_build_achievement_messages_truncates_long_window_message(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    candidates = [_achievement()]
    long_message = "x" * (ACHIEVEMENT_EXCERPT_CHARS + 50)
    window = [ChatMessage(role="user", content=long_message)]

    messages = build_achievement_messages(scenario, candidates, "ação", "ok", window)
    body = messages[1].content

    assert long_message not in body
    assert ("x" * ACHIEVEMENT_EXCERPT_CHARS) in body


def test_build_achievement_messages_does_not_leak_name_hint_rarity(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    candidates = [
        AchievementDef(
            id="ach-1",
            name="Nome Secreto",
            type="achievement",
            rarity="legendary",
            hint="dica escondida",
            condition="fez algo",
        )
    ]

    messages = build_achievement_messages(scenario, candidates, "ação", "ok", [])
    body = messages[1].content

    assert "Nome Secreto" not in body
    assert "dica escondida" not in body
    assert "legendary" not in body


def test_build_achievement_messages_en_locale_uses_english_template(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en")
    candidates = [_achievement()]

    messages = build_achievement_messages(scenario, candidates, "enters the room", "ok", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "AÇÃO DO JOGADOR" not in prompt_text
    assert "PLAYER ACTION" in prompt_text


def test_build_achievement_messages_unknown_locale_falls_back_to_ptbr(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    scenario.meta.locale = "fr"
    candidates = [_achievement()]

    messages = build_achievement_messages(scenario, candidates, "ação", "ok", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "AÇÃO DO JOGADOR" in prompt_text


# --- schema ------------------------------------------------------------------


def test_achievements_options_schema_shape():
    schema = ACHIEVEMENTS_OPTIONS.json_schema
    assert schema["required"] == ["verdicts"]
    verdict_schema = AchievementsResponse.model_json_schema()["$defs"]["AchievementVerdict"]
    assert verdict_schema["additionalProperties"] is False
    assert set(verdict_schema["required"]) == {"id", "met"}
    assert AchievementsResponse.model_json_schema()["additionalProperties"] is False


def test_judge_achievements_builds_provider_with_achievements_options(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    captured = {}
    original_init = OpenAICompatProvider.__init__

    def spy_init(self, provider_config, options):
        captured["options"] = options
        original_init(self, provider_config, options)

    monkeypatch.setattr(OpenAICompatProvider, "__init__", spy_init)

    _judge_with_response(scenario, [_achievement()], monkeypatch, '{"verdicts": []}')

    assert captured["options"] is ACHIEVEMENTS_OPTIONS


def test_judge_achievements_payload_carries_schema_when_structured_output_enabled(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    async def fake_stream(self, messages, model):
        yield '{"verdicts": []}'

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    asyncio.run(
        judge_achievements(
            scenario, [_achievement()], "ação", "ok", [], _config(structured_output="json_schema")
        )
    )

    provider = OpenAICompatProvider(_config(structured_output="json_schema").providers["local"], ACHIEVEMENTS_OPTIONS)
    payload = provider.build_payload([], "m")
    assert payload["response_format"]["json_schema"]["name"] == "achievements"


def test_judge_achievements_payload_has_no_response_format_when_disabled():
    provider = OpenAICompatProvider(_config(structured_output="none").providers["local"], ACHIEVEMENTS_OPTIONS)
    payload = provider.build_payload([], "m")
    assert "response_format" not in payload


# --- parse_achievements --------------------------------------------------------


def test_parse_achievements_accepts_envelope():
    data, reason = parse_achievements('{"verdicts": [{"id": "a", "met": true}]}')
    assert data == [{"id": "a", "met": True}]
    assert reason is None


def test_parse_achievements_accepts_raw_list_at_root():
    data, reason = parse_achievements('[{"id": "a", "met": true}]')
    assert data == [{"id": "a", "met": True}]
    assert reason is None


def test_parse_achievements_accepts_envelope_in_code_fence():
    raw = '```json\n{"verdicts": [{"id": "a", "met": false}]}\n```'
    data, reason = parse_achievements(raw)
    assert data == [{"id": "a", "met": False}]
    assert reason is None


def test_parse_achievements_accepts_raw_list_in_code_fence():
    raw = '```json\n[{"id": "a", "met": false}]\n```'
    data, reason = parse_achievements(raw)
    assert data == [{"id": "a", "met": False}]
    assert reason is None


@pytest.mark.parametrize("raw", ["", "   ", "tudo calmo por aqui"])
def test_parse_achievements_prose_and_empty_are_invalid(raw):
    assert parse_achievements(raw) == (None, "invalid_json")


# --- apply_verdicts --------------------------------------------------------------


def test_apply_verdicts_one_met_one_not_met():
    candidates = [_achievement(id="a"), _achievement(id="b")]
    verdicts = [{"id": "a", "met": True}, {"id": "b", "met": False}]

    unlocked, rejections = apply_verdicts(candidates, verdicts)

    assert [a.id for a in unlocked] == ["a"]
    assert rejections == []


def test_apply_verdicts_two_endings_met_keeps_first_declared():
    first_ending = _achievement(id="ending-1", type="ending")
    second_ending = _achievement(id="ending-2", type="ending")
    verdicts = [{"id": "ending-1", "met": True}, {"id": "ending-2", "met": True}]

    unlocked, rejections = apply_verdicts([first_ending, second_ending], verdicts)

    assert [a.id for a in unlocked] == ["ending-1"]
    assert len(rejections) == 1
    assert rejections[0].id == "ending-2"
    assert rejections[0].reason == "another_ending"


def test_apply_verdicts_achievement_and_ending_both_met():
    achievement = _achievement(id="a", type="achievement")
    ending = _achievement(id="e", type="ending")
    verdicts = [{"id": "a", "met": True}, {"id": "e", "met": True}]

    unlocked, rejections = apply_verdicts([achievement, ending], verdicts)

    assert {a.id for a in unlocked} == {"a", "e"}
    assert rejections == []


def test_apply_verdicts_not_a_candidate_duplicate_and_not_a_bool():
    candidates = [_achievement(id="a")]
    verdicts = [
        {"id": "unknown", "met": True},
        {"id": "a", "met": True},
        {"id": "a", "met": False},
        {"id": "a", "met": "sim"},
    ]

    unlocked, rejections = apply_verdicts(candidates, verdicts)

    assert [a.id for a in unlocked] == ["a"]
    reasons = {(r.id, r.reason) for r in rejections}
    assert ("unknown", "not_a_candidate") in reasons
    assert ("a", "duplicate_id") in reasons


def test_apply_verdicts_not_a_bool_alone():
    candidates = [_achievement(id="a")]
    verdicts = [{"id": "a", "met": "sim"}]

    unlocked, rejections = apply_verdicts(candidates, verdicts)

    assert unlocked == []
    assert len(rejections) == 1
    assert rejections[0].id == "a"
    assert rejections[0].reason == "not_a_bool"


# --- judge_achievements ----------------------------------------------------------


def test_judge_achievements_no_utility_role_raises_without_calling_provider(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    called = []

    async def fake_stream(self, messages, model):
        called.append(True)
        yield "should not run"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(AchievementError, match="no utility role"):
        asyncio.run(
            judge_achievements(
                scenario, [_achievement()], "oi", "nada", [], _config_without_utility()
            )
        )

    assert called == []


def test_judge_achievements_empty_candidates_raises():
    with pytest.raises(AchievementError):
        asyncio.run(judge_achievements(None, [], "oi", "nada", [], _config_without_utility()))


def test_judge_achievements_provider_error_becomes_achievement_error(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    async def fake_stream(self, messages, model):
        raise RuntimeError("boom")
        yield ""

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(AchievementError):
        asyncio.run(judge_achievements(scenario, [_achievement()], "oi", "nada", [], _config()))


def test_judge_achievements_happy_path_returns_verdicts_and_raw(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    raw = '{"verdicts": [{"id": "ach-1", "met": true}]}'

    verdicts, reason, returned_raw = _judge_with_response(scenario, [_achievement()], monkeypatch, raw)

    assert verdicts == [{"id": "ach-1", "met": True}]
    assert reason is None
    assert returned_raw == raw


def test_judge_achievements_prose_response_is_invalid(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    raw = "tudo calmo, nada aconteceu"

    verdicts, reason, returned_raw = _judge_with_response(scenario, [_achievement()], monkeypatch, raw)

    assert verdicts is None
    assert reason == "invalid_json"
    assert returned_raw == raw
