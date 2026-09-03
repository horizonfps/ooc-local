import asyncio

import pytest

from app.config import Config
from app.hud import DynamicStat, HudState
from app.judge import (
    DYNAMIC_STAT_NAME_CHARS,
    JUDGE_NARRATOR_CHARS,
    JUDGE_OPTIONS,
    JudgeError,
    StatChange,
    StatRejection,
    apply_judgement,
    build_judge_messages,
    judge_turn,
    parse_judgement,
)
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import load_scenario

WORLD_MD = "# Mundo\n\nUma escola nas montanhas.\n"

SCENARIO_YAML_PTBR = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
allow_dynamic_stats: {allow_dynamic_stats}
{max_dynamic_stats_line}"""

SCENARIO_YAML_EN = """\
name: Example School
tagline: a tagline
locale: en
allow_dynamic_stats: {allow_dynamic_stats}
{max_dynamic_stats_line}"""

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
  description: Quanto a escola te respeita.
- id: energia
  name: Energia
  min: 0
  max: 100
  default: 80
"""

STATS_YAML_MAX_DELTA = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 50
  description: Quanto a escola te respeita.
  max_delta: 5
- id: energia
  name: Energia
  min: 0
  max: 100
  default: 80
"""


def _write_scenario(
    root, scenario_id="exemplo-escola", *, locale="pt-br", allow_dynamic_stats=False, max_dynamic_stats=None
):
    scenario_yaml = SCENARIO_YAML_PTBR if locale == "pt-br" else SCENARIO_YAML_EN
    max_dynamic_stats_line = f"max_dynamic_stats: {max_dynamic_stats}\n" if max_dynamic_stats is not None else ""
    scenario_yaml = scenario_yaml.format(
        allow_dynamic_stats=str(allow_dynamic_stats).lower(),
        max_dynamic_stats_line=max_dynamic_stats_line,
    )

    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")
    (scenario_path / "stats.yaml").write_text(STATS_YAML, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    return scenario_path


def _load(monkeypatch, tmp_path, *, locale="pt-br", allow_dynamic_stats=False, max_dynamic_stats=None):
    _write_scenario(
        tmp_path, locale=locale, allow_dynamic_stats=allow_dynamic_stats, max_dynamic_stats=max_dynamic_stats
    )
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return load_scenario("exemplo-escola")


def _load_with_stats_yaml(monkeypatch, tmp_path, stats_yaml, *, allow_dynamic_stats=False):
    _write_scenario(tmp_path, allow_dynamic_stats=allow_dynamic_stats)
    (tmp_path / "exemplo-escola" / "stats.yaml").write_text(stats_yaml, encoding="utf-8")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return load_scenario("exemplo-escola")


def _hud(**overrides) -> HudState:
    base = dict(turn=3, location="patio", time="09:30", weather="cloudy", stats={"reputacao": 50, "energia": 80})
    base.update(overrides)
    return HudState(**base)


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


def _judge_with_response(scenario, monkeypatch, raw, *, hud=None, message="ameaça a aluna", narrator_text="ela recua", touched_ids=None, config=None):
    async def fake_stream(self, messages, model):
        yield raw

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    return asyncio.run(
        judge_turn(
            scenario,
            hud or _hud(),
            message,
            narrator_text,
            touched_ids or [],
            config or _config(),
        )
    )


# --- parse_judgement ---------------------------------------------------------


def test_parse_judgement_happy_path():
    assert parse_judgement('{"stats": {"reputacao": -5}}') == ({"stats": {"reputacao": -5}}, None)


def test_parse_judgement_accepts_code_fence_and_surrounding_prose():
    raw = 'claro:\n```json\n{"stats": {}}\n```\npronto'
    assert parse_judgement(raw) == ({"stats": {}}, None)


def test_parse_judgement_accepts_explicit_plus_sign():
    raw = '```json\n{"stats": {"reputacao": +5, "energia": -3}}\n```'
    assert parse_judgement(raw) == ({"stats": {"reputacao": 5, "energia": -3}}, None)


def test_parse_judgement_keeps_plus_inside_strings():
    data, _ = parse_judgement('{"stats": {}, "nota": "+5 de moral"}')
    assert data == {"stats": {}, "nota": "+5 de moral"}


def test_parse_judgement_empty_object_is_legit():
    assert parse_judgement("{}") == ({}, None)


def test_parse_judgement_extra_key_is_ignored():
    data, reason = parse_judgement('{"stats": {}, "comentario": "tudo calmo"}')
    assert data == {"stats": {}, "comentario": "tudo calmo"}
    assert reason is None


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "a reputação cai", '{"stats": {', '[{"stats": {}}]'],
)
def test_parse_judgement_malformed_is_invalid(raw):
    assert parse_judgement(raw) == (None, "invalid_json")


# --- apply_judgement: existing stats -----------------------------------------


def test_apply_judgement_happy_path(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    new_hud, changes, rejected = apply_judgement(scenario, _hud(), {"stats": {"reputacao": -5}}, [])

    assert new_hud.stats["reputacao"] == 45
    assert changes == [StatChange(id="reputacao", delta=-5, value=45, source="judge")]
    assert rejected == []


def test_apply_judgement_two_ids_in_json_order(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    new_hud, changes, rejected = apply_judgement(
        scenario, _hud(), {"stats": {"energia": -3, "reputacao": 2}}, []
    )

    assert [c.id for c in changes] == ["energia", "reputacao"]
    assert new_hud.stats["energia"] == 77
    assert new_hud.stats["reputacao"] == 52
    assert rejected == []


def test_apply_judgement_delta_without_max_delta_moves_freely(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    _, changes, _ = apply_judgement(scenario, _hud(), {"stats": {"reputacao": 40}}, [])
    assert changes[0].delta == 40
    assert changes[0].value == 90


def test_apply_judgement_delta_clamped_to_stat_max_delta(monkeypatch, tmp_path):
    scenario = _load_with_stats_yaml(monkeypatch, tmp_path, STATS_YAML_MAX_DELTA)

    _, changes, _ = apply_judgement(scenario, _hud(), {"stats": {"reputacao": 40}}, [])
    assert changes[0].delta == 5
    assert changes[0].value == 55

    _, changes, _ = apply_judgement(scenario, _hud(), {"stats": {"reputacao": -999}}, [])
    assert changes[0].delta == -5
    assert changes[0].value == 45


def test_apply_judgement_max_delta_does_not_override_range_clamp(monkeypatch, tmp_path):
    scenario = _load_with_stats_yaml(monkeypatch, tmp_path, STATS_YAML_MAX_DELTA)
    hud = _hud(stats={"reputacao": 98, "energia": 80})

    _, changes, _ = apply_judgement(scenario, hud, {"stats": {"reputacao": 40}}, [])

    assert changes[0].delta == 2
    assert changes[0].value == 100


def test_apply_judgement_value_clamped_to_stat_range(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    hud = _hud(stats={"reputacao": 98, "energia": 80})

    _, changes, _ = apply_judgement(scenario, hud, {"stats": {"reputacao": 5}}, [])

    assert changes[0].value == 100
    assert changes[0].delta == 2


def test_apply_judgement_at_max_with_positive_delta_is_no_change(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    hud = _hud(stats={"reputacao": 100, "energia": 80})

    new_hud, changes, rejected = apply_judgement(scenario, hud, {"stats": {"reputacao": 5}}, [])

    assert changes == []
    assert rejected == [StatRejection(id="reputacao", reason="no_change")]
    assert new_hud is hud


def test_apply_judgement_existing_dynamic_stat_accepts_delta(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    hud = _hud(dynamic_stats={"vida": DynamicStat(name="Vida", value=50, min=0, max=100)})

    new_hud, changes, rejected = apply_judgement(scenario, hud, {"stats": {"vida": -10}}, [])

    assert new_hud.dynamic_stats["vida"].value == 40
    assert changes == [StatChange(id="vida", delta=-10, value=40, source="judge")]
    assert rejected == []


@pytest.mark.parametrize(
    "judgement, touched_ids, expected",
    [
        ({"stats": {"fantasma": -3}}, [], StatRejection(id="fantasma", reason="unknown_id")),
        ({"stats": {"reputacao": -5}}, ["reputacao"], StatRejection(id="reputacao", reason="touched_by_tag")),
        ({"stats": {"reputacao": True}}, [], StatRejection(id="reputacao", reason="not_an_int")),
        ({"stats": {"reputacao": "muito"}}, [], StatRejection(id="reputacao", reason="not_an_int")),
        ({"stats": []}, [], StatRejection(id="stats", reason="not_a_map")),
    ],
)
def test_apply_judgement_stats_named_rejections_leave_hud_intact(monkeypatch, tmp_path, judgement, touched_ids, expected):
    scenario = _load(monkeypatch, tmp_path)
    hud = _hud()

    new_hud, changes, rejected = apply_judgement(scenario, hud, judgement, touched_ids)

    assert changes == []
    assert rejected == [expected]
    assert new_hud is hud


def test_apply_judgement_empty_object_is_noop(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    hud = _hud()

    new_hud, changes, rejected = apply_judgement(scenario, hud, {}, [])

    assert new_hud is hud
    assert changes == []
    assert rejected == []


# --- apply_judgement: new dynamic stats --------------------------------------


def test_apply_judgement_creates_dynamic_stat(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)
    hud = _hud()

    new_hud, changes, rejected = apply_judgement(
        scenario, hud, {"new": [{"id": "vida", "name": "Vida", "value": 110, "max": 110}]}, []
    )

    assert new_hud.dynamic_stats["vida"] == DynamicStat(name="Vida", value=110, min=0, max=110)
    assert changes == [StatChange(id="vida", delta=0, value=110, source="judge")]
    assert rejected == []


def test_apply_judgement_new_stat_value_and_name_clamped(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)
    long_name = "x" * 90

    new_hud, changes, _ = apply_judgement(
        scenario,
        _hud(),
        {"new": [{"id": "vida", "name": long_name, "value": 999, "max": 110}]},
        [],
    )

    assert new_hud.dynamic_stats["vida"].value == 110
    assert new_hud.dynamic_stats["vida"].name == ("x" * DYNAMIC_STAT_NAME_CHARS)


def test_apply_judgement_new_disabled_is_a_single_rejection(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=False)
    hud = _hud()

    new_hud, changes, rejected = apply_judgement(
        scenario, hud, {"new": [{"id": "vida", "name": "Vida", "value": 10, "max": 100}]}, []
    )

    assert changes == []
    assert rejected == [StatRejection(id="new", reason="dynamic_disabled")]
    assert new_hud is hud
    assert hud.dynamic_stats == {}


@pytest.mark.parametrize(
    "new_field, expected",
    [
        ("vida", StatRejection(id="new", reason="not_a_list")),
        (
            [{"id": "vida", "name": "Vida", "value": 10}],
            StatRejection(id="vida", reason="invalid_shape"),
        ),
        (
            [{"id": "vida", "name": "Vida", "value": 10, "max": 5, "min": 5}],
            StatRejection(id="vida", reason="invalid_shape"),
        ),
        (
            [{"id": "vida", "name": "Vida", "value": "dez", "max": 100}],
            StatRejection(id="vida", reason="invalid_shape"),
        ),
        (
            [{"id": "Vida!", "name": "Vida", "value": 10, "max": 100}],
            StatRejection(id="Vida!", reason="invalid_id"),
        ),
        (
            [{"id": "reputacao", "name": "Rep", "value": 10, "max": 100}],
            StatRejection(id="reputacao", reason="duplicate_id"),
        ),
    ],
)
def test_apply_judgement_new_named_rejections(monkeypatch, tmp_path, new_field, expected):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)

    _, changes, rejected = apply_judgement(scenario, _hud(), {"new": new_field}, [])

    assert changes == []
    assert rejected == [expected]


def test_apply_judgement_new_duplicate_within_same_call(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)
    item = {"id": "vida", "name": "Vida", "value": 10, "max": 100}

    new_hud, changes, rejected = apply_judgement(scenario, _hud(), {"new": [item, item]}, [])

    assert len(changes) == 1
    assert rejected == [StatRejection(id="vida", reason="duplicate_id")]
    assert "vida" in new_hud.dynamic_stats


def test_apply_judgement_new_over_cap_when_hud_already_full(monkeypatch, tmp_path):
    cap = 6
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True, max_dynamic_stats=cap)
    dynamic_stats = {f"stat{i}": DynamicStat(name=f"Stat{i}", value=1, min=0, max=10) for i in range(cap)}
    hud = _hud(dynamic_stats=dynamic_stats)

    new_hud, changes, rejected = apply_judgement(
        scenario, hud, {"new": [{"id": "vida", "name": "Vida", "value": 10, "max": 100}]}, []
    )

    assert changes == []
    assert rejected == [StatRejection(id="vida", reason="over_cap")]
    assert new_hud is hud


def test_apply_judgement_new_over_cap_only_first_of_three_accepted(monkeypatch, tmp_path):
    cap = 6
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True, max_dynamic_stats=cap)
    dynamic_stats = {f"stat{i}": DynamicStat(name=f"Stat{i}", value=1, min=0, max=10) for i in range(cap - 1)}
    hud = _hud(dynamic_stats=dynamic_stats)
    items = [
        {"id": "vida", "name": "Vida", "value": 10, "max": 100},
        {"id": "mana", "name": "Mana", "value": 10, "max": 100},
        {"id": "sede", "name": "Sede", "value": 10, "max": 100},
    ]

    new_hud, changes, rejected = apply_judgement(scenario, hud, {"new": items}, [])

    assert [c.id for c in changes] == ["vida"]
    assert [r.id for r in rejected] == ["mana", "sede"]
    assert all(r.reason == "over_cap" for r in rejected)
    assert "vida" in new_hud.dynamic_stats


def test_apply_judgement_new_without_cap_accepts_beyond_thirty(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)
    dynamic_stats = {f"stat{i}": DynamicStat(name=f"Stat{i}", value=1, min=0, max=10) for i in range(30)}
    hud = _hud(dynamic_stats=dynamic_stats)

    new_hud, changes, rejected = apply_judgement(
        scenario, hud, {"new": [{"id": "vida", "name": "Vida", "value": 10, "max": 100}]}, []
    )

    assert changes == [StatChange(id="vida", delta=0, value=10, source="judge")]
    assert rejected == []
    assert "vida" in new_hud.dynamic_stats


def test_apply_judgement_new_kind_item_is_stored(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)

    new_hud, changes, rejected = apply_judgement(
        scenario,
        _hud(),
        {"new": [{"id": "espada", "name": "Espada", "value": 1, "max": 1, "kind": "item"}]},
        [],
    )

    assert new_hud.dynamic_stats["espada"].kind == "item"
    assert rejected == []


def test_apply_judgement_new_without_kind_defaults_to_stat(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)

    new_hud, changes, rejected = apply_judgement(
        scenario, _hud(), {"new": [{"id": "vida", "name": "Vida", "value": 10, "max": 100}]}, []
    )

    assert new_hud.dynamic_stats["vida"].kind == "stat"
    assert rejected == []


def test_apply_judgement_new_invalid_kind_is_rejected(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)
    hud = _hud()

    new_hud, changes, rejected = apply_judgement(
        scenario,
        hud,
        {"new": [{"id": "espada", "name": "Espada", "value": 1, "max": 1, "kind": "weapon"}]},
        [],
    )

    assert changes == []
    assert rejected == [StatRejection(id="espada", reason="invalid_kind")]
    assert new_hud is hud
    assert hud.dynamic_stats == {}


@pytest.mark.parametrize("bad_kind", [5, None])
def test_apply_judgement_new_non_string_kind_is_rejected(monkeypatch, tmp_path, bad_kind):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)
    hud = _hud()

    new_hud, changes, rejected = apply_judgement(
        scenario,
        hud,
        {"new": [{"id": "espada", "name": "Espada", "value": 1, "max": 1, "kind": bad_kind}]},
        [],
    )

    assert changes == []
    assert rejected == [StatRejection(id="espada", reason="invalid_kind")]
    assert new_hud is hud
    assert hud.dynamic_stats == {}


def test_apply_judgement_new_invalid_kind_rejected_before_over_cap(monkeypatch, tmp_path):
    cap = 1
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True, max_dynamic_stats=cap)
    dynamic_stats = {"stat0": DynamicStat(name="Stat0", value=1, min=0, max=10)}
    hud = _hud(dynamic_stats=dynamic_stats)
    items = [
        {"id": "espada", "name": "Espada", "value": 1, "max": 1, "kind": "weapon"},
        {"id": "vida", "name": "Vida", "value": 10, "max": 100, "kind": "item"},
    ]

    new_hud, changes, rejected = apply_judgement(scenario, hud, {"new": items}, [])

    assert changes == []
    assert [r.id for r in rejected] == ["espada", "vida"]
    assert [r.reason for r in rejected] == ["invalid_kind", "over_cap"]
    assert new_hud is hud
    assert hud.dynamic_stats == dynamic_stats


def test_apply_judgement_stats_before_new_order(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, allow_dynamic_stats=True)

    new_hud, changes, rejected = apply_judgement(
        scenario,
        _hud(),
        {"stats": {"vida": -3}, "new": [{"id": "vida", "name": "Vida", "value": 100, "max": 100}]},
        [],
    )

    assert StatRejection(id="vida", reason="unknown_id") in rejected
    assert "vida" in new_hud.dynamic_stats
    assert any(c.id == "vida" and c.delta == 0 for c in changes)


# --- build_judge_messages -----------------------------------------------------


def test_build_judge_messages_lists_declared_stats(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    messages = build_judge_messages(scenario, _hud(), "ameaça a aluna", "ela recua", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "reputacao | Reputação | 50/0..100 | Quanto a escola te respeita." in prompt_text
    assert "energia | Energia | 80/0..100" in prompt_text
    assert "energia | Energia | 80/0..100 |" not in prompt_text


def test_build_judge_messages_marks_only_touched_stat(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    messages = build_judge_messages(scenario, _hud(), "oi", "nada", ["energia"])
    prompt_text = "\n".join(m.content for m in messages)

    energia_line = next(line for line in prompt_text.split("\n") if line.startswith("energia |"))
    reputacao_line = next(line for line in prompt_text.split("\n") if line.startswith("reputacao |"))

    assert "já ajustado neste turno" in energia_line
    assert "já ajustado neste turno" not in reputacao_line


def test_build_judge_messages_cuts_narration(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    narration = "x" * 5000

    messages = build_judge_messages(scenario, _hud(), "oi", narration, [])
    prompt_text = "\n".join(m.content for m in messages)

    assert ("x" * JUDGE_NARRATOR_CHARS) in prompt_text
    assert ("x" * (JUDGE_NARRATOR_CHARS + 1)) not in prompt_text


def test_build_judge_messages_uses_stat_default_when_hud_stats_empty(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    hud = HudState(turn=0, location="patio", time="09:30", weather="cloudy")

    messages = build_judge_messages(scenario, hud, "oi", "nada", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "reputacao | Reputação | 50/0..100" in prompt_text
    assert "energia | Energia | 80/0..100" in prompt_text


def test_build_judge_messages_marks_max_delta_on_the_stat_line(monkeypatch, tmp_path):
    scenario = _load_with_stats_yaml(monkeypatch, tmp_path, STATS_YAML_MAX_DELTA)

    messages = build_judge_messages(scenario, _hud(), "ameaça a aluna", "ela recua", [])
    prompt_text = "\n".join(m.content for m in messages)

    reputacao_line = next(line for line in prompt_text.split("\n") if line.startswith("reputacao |"))
    energia_line = next(line for line in prompt_text.split("\n") if line.startswith("energia |"))

    assert " | max ±5" in reputacao_line
    assert "max ±" not in energia_line


def test_build_judge_messages_max_delta_and_touched_marker_order(monkeypatch, tmp_path):
    scenario = _load_with_stats_yaml(monkeypatch, tmp_path, STATS_YAML_MAX_DELTA)

    messages = build_judge_messages(scenario, _hud(), "ameaça a aluna", "ela recua", ["reputacao"])
    prompt_text = "\n".join(m.content for m in messages)

    reputacao_line = next(line for line in prompt_text.split("\n") if line.startswith("reputacao |"))

    assert reputacao_line.endswith("max ±5 (já ajustado neste turno)")


def test_build_judge_messages_system_prompts_never_mention_fixed_delta(monkeypatch, tmp_path):
    ptbr = _load(monkeypatch, tmp_path)
    en = _load(monkeypatch, tmp_path / "en", locale="en")

    ptbr_system = build_judge_messages(ptbr, _hud(), "oi", "nada", [])[0].content
    en_system = build_judge_messages(en, _hud(), "enters", "ok", [])[0].content

    for system in (ptbr_system, en_system):
        assert "-10" not in system
        assert "+10" not in system


def test_build_judge_messages_dynamic_stats_flag_controls_kind_mention(monkeypatch, tmp_path):
    disabled = _load(monkeypatch, tmp_path, allow_dynamic_stats=False)
    enabled = _load(monkeypatch, tmp_path / "enabled", allow_dynamic_stats=True)

    disabled_system = build_judge_messages(disabled, _hud(), "oi", "nada", [])[0].content
    enabled_system = build_judge_messages(enabled, _hud(), "oi", "nada", [])[0].content

    assert "kind" not in disabled_system
    assert "kind" in enabled_system
    assert "item" in enabled_system
    assert "skill" in enabled_system


def test_build_judge_messages_en_system_prompt_has_max_delta_rule_and_kinds(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en", allow_dynamic_stats=True)

    system = build_judge_messages(scenario, _hud(), "enters the room", "ok", [])[0].content

    assert "max ±N" in system
    assert "item" in system
    assert "skill" in system


def test_build_judge_messages_dynamic_stats_flag_controls_system_text(monkeypatch, tmp_path):
    disabled = _load(monkeypatch, tmp_path, allow_dynamic_stats=False)
    enabled = _load(monkeypatch, tmp_path / "enabled", allow_dynamic_stats=True)

    disabled_system = build_judge_messages(disabled, _hud(), "oi", "nada", [])[0].content
    enabled_system = build_judge_messages(enabled, _hud(), "oi", "nada", [])[0].content

    assert "new" not in disabled_system
    assert "new" in enabled_system


def test_build_judge_messages_flattens_pipes_and_newlines(monkeypatch, tmp_path):
    evil_stats = STATS_YAML.replace(
        "name: Reputação", 'name: "Reputação\\ndo | clube"'
    )
    _write_scenario(tmp_path, allow_dynamic_stats=False)
    (tmp_path / "exemplo-escola" / "stats.yaml").write_text(evil_stats, encoding="utf-8")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    scenario = load_scenario("exemplo-escola")

    messages = build_judge_messages(scenario, _hud(), "oi", "nada", [])
    body = messages[1].content
    line = next(line for line in body.split("\n") if line.startswith("reputacao |"))

    assert line.startswith("reputacao | Reputação do / clube | 50/0..100")


def test_build_judge_messages_en_locale_has_no_ptbr_words(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en")

    messages = build_judge_messages(scenario, _hud(), "enters the room", "ok", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "AÇÃO DO JOGADOR" not in prompt_text
    assert "PLAYER ACTION" in prompt_text


def test_build_judge_messages_ptbr_locale_has_no_en_words(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="pt-br")

    messages = build_judge_messages(scenario, _hud(), "entra na sala", "ok", [])
    prompt_text = "\n".join(m.content for m in messages)

    assert "PLAYER ACTION" not in prompt_text


# --- judge_turn ----------------------------------------------------------------


def test_judge_turn_happy_path_returns_judgement_and_raw(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    raw = '{"stats": {"reputacao": -5}}'

    judgement, reason, returned_raw = _judge_with_response(scenario, monkeypatch, raw)

    assert judgement == {"stats": {"reputacao": -5}}
    assert reason is None
    assert returned_raw == raw


def test_judge_turn_builds_provider_with_judge_options(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    captured = {}
    original_init = OpenAICompatProvider.__init__

    def spy_init(self, provider_config, options):
        captured["options"] = options
        original_init(self, provider_config, options)

    monkeypatch.setattr(OpenAICompatProvider, "__init__", spy_init)

    _judge_with_response(scenario, monkeypatch, '{"stats": {}}')

    assert captured["options"] is JUDGE_OPTIONS


def test_judge_turn_no_utility_role_raises_without_calling_provider(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    called = []

    async def fake_stream(self, messages, model):
        called.append(True)
        yield "should not run"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(JudgeError, match="no utility role"):
        asyncio.run(
            judge_turn(scenario, _hud(), "oi", "nada", [], _config_without_utility())
        )

    assert called == []


def test_judge_turn_provider_error_becomes_judge_error(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    async def fake_stream(self, messages, model):
        raise RuntimeError("boom")
        yield ""

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with pytest.raises(JudgeError):
        asyncio.run(judge_turn(scenario, _hud(), "oi", "nada", [], _config()))


def test_judge_turn_whitespace_only_response_is_invalid(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    judgement, reason, raw = _judge_with_response(scenario, monkeypatch, "   ")

    assert judgement is None
    assert reason == "invalid_json"
    assert raw == "   "


def test_judge_options_tokens_temperature_timeout():
    assert JUDGE_OPTIONS.max_tokens == 200
    assert JUDGE_OPTIONS.temperature == 0.1
    assert JUDGE_OPTIONS.timeout_s == 45.0
