import json

import pytest
from fastapi.testclient import TestClient

from app import main, sessions, turn
from app.config import Config
from app.hud import (
    STAT_EVENT_KIND,
    DynamicStat,
    HudState,
    apply_stat,
    ensure_stats,
    stat_event,
    stat_ids,
)
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import StatDef, StatLevel

# --- pure function unit tests -----------------------------------------------

REPUTACAO = StatDef(id="reputacao", name="Reputação", min=0, max=100, default=40)


def _hud(**stats):
    return HudState(location="patio", time="08:00", weather="clear", stats=stats)


def test_apply_stat_happy_path_delta_and_no_mutation():
    hud = _hud(reputacao=40)

    new_hud, change = apply_stat(hud, [REPUTACAO], "reputacao", 5)

    assert change == (5, 45)
    assert new_hud.stats["reputacao"] == 45
    assert hud.stats["reputacao"] == 40


def test_apply_stat_clamps_at_max_then_second_delta_is_no_change():
    hud = _hud(reputacao=40)

    new_hud, change = apply_stat(hud, [REPUTACAO], "reputacao", 100)
    assert change == (60, 100)
    assert new_hud.stats["reputacao"] == 100

    same_hud, no_change = apply_stat(new_hud, [REPUTACAO], "reputacao", 5)
    assert no_change is None
    assert same_hud is new_hud


def test_apply_stat_clamps_at_min():
    hud = _hud(reputacao=40)

    new_hud, change = apply_stat(hud, [REPUTACAO], "reputacao", -100)

    assert change == (-40, 0)
    assert new_hud.stats["reputacao"] == 0


def test_apply_stat_unknown_id_is_noop():
    hud = _hud(reputacao=40)

    new_hud, change = apply_stat(hud, [REPUTACAO], "fantasma", 1)

    assert change is None
    assert new_hud is hud
    assert "fantasma" not in new_hud.stats


def test_apply_stat_on_dynamic_stat_clamps_by_its_own_range_and_writes_dynamic_stats():
    hud = HudState(
        location="patio",
        time="08:00",
        weather="clear",
        dynamic_stats={"sanidade": DynamicStat(name="Sanidade", value=3, max=10)},
    )

    new_hud, change = apply_stat(hud, [], "sanidade", 100)

    assert change == (7, 10)
    assert new_hud.dynamic_stats["sanidade"].value == 10
    assert new_hud.stats == {}


def test_ensure_stats_fills_only_missing_and_preserves_existing_value():
    hud = _hud(reputacao=55)
    energia = StatDef(id="energia", name="Energia", min=0, max=10, default=5)

    filled = ensure_stats(hud, [REPUTACAO, energia])

    assert filled.stats == {"reputacao": 55, "energia": 5}


def test_ensure_stats_reclamps_value_left_outside_an_edited_range():
    hud = _hud(reputacao=80)
    narrowed = StatDef(id="reputacao", name="Reputação", min=0, max=50, default=40)

    filled = ensure_stats(hud, [narrowed])

    assert filled.stats == {"reputacao": 50}
    assert hud.stats == {"reputacao": 80}


def test_ensure_stats_returns_same_object_when_nothing_to_fill():
    hud = _hud(reputacao=55)

    filled = ensure_stats(hud, [REPUTACAO])

    assert filled is hud


def test_ensure_stats_preserves_stat_key_removed_from_scenario():
    hud = _hud(extinto=999)

    filled = ensure_stats(hud, [REPUTACAO])

    assert filled.stats == {"extinto": 999, "reputacao": 40}


def test_stat_ids_unions_declared_and_dynamic():
    hud = HudState(
        location="patio",
        time="08:00",
        weather="clear",
        dynamic_stats={"sanidade": DynamicStat(name="Sanidade", value=3, max=10)},
    )

    assert stat_ids(hud, [REPUTACAO]) == {"reputacao", "sanidade"}


def test_stat_event_contract():
    kind, payload = stat_event("reputacao", -5, 35, "tag")

    assert kind == STAT_EVENT_KIND
    assert payload == {"id": "reputacao", "delta": -5, "value": 35, "source": "tag"}


# --- prompt tests ------------------------------------------------------------

from app.prompt import build_master_prompt  # noqa: E402
from app.scenario import load_scenario  # noqa: E402

_PROMPT_WORLD_MD = "# Mundo\n\nUma escola.\n"

_PROMPT_SCENARIO_YAML = {
    "pt-br": "name: Exemplo Escola\ntagline: uma tagline\nlocale: pt-br\n",
    "en": "name: Example School\ntagline: a tagline\nlocale: en\n",
}

_PROMPT_DEFAULT_START = (
    "name: Começo\nprologue: prologo\nopening_scene: cena\nhud:\n  location: patio\n  time: \"08:00\"\n"
)

_PROMPT_CHLOE_YAML = (
    "name: Chloe\nrole: aluna\nappearance: baixa\npersonality: extrovertida\nvoice: animada\n"
    "mind:\n  feeling: curiosa\n  goal: descobrir segredo\n"
)

_PROMPT_TWO_STATS_YAML = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 40
- id: energia
  name: Energia
  min: 0
  max: 100
  default: 80
"""


def _load_prompt_scenario(tmp_path, monkeypatch, *, locale="pt-br", stats=None):
    root = tmp_path / f"scenarios-{locale}-{'with-stats' if stats else 'no-stats'}"
    scenario_path = root / "exemplo-escola"
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(_PROMPT_SCENARIO_YAML[locale], encoding="utf-8")
    (scenario_path / "world.md").write_text(_PROMPT_WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(_PROMPT_DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(_PROMPT_CHLOE_YAML, encoding="utf-8")

    if stats is not None:
        (scenario_path / "stats.yaml").write_text(stats, encoding="utf-8")

    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)
    scenario = load_scenario("exemplo-escola")
    return scenario, scenario.starts["default"]


def test_prompt_status_section_appears_between_hud_and_opening_with_one_line_per_stat(
    tmp_path, monkeypatch
):
    scenario, start = _load_prompt_scenario(tmp_path, monkeypatch, stats=_PROMPT_TWO_STATS_YAML)
    hud = HudState(location="patio", time="08:00", weather="clear", stats={"reputacao": 55, "energia": 80})

    prompt = build_master_prompt(scenario, start, hud, [])

    hud_pos = prompt.index("## ESTADO DO JOGO")
    status_pos = prompt.index("## STATUS DO JOGADOR")
    opening_pos = prompt.index("## CENA DE ABERTURA")
    assert hud_pos < status_pos < opening_pos

    status_section = prompt[status_pos:opening_pos]
    lines = [line for line in status_section.split("\n") if line and not line.startswith("#")]
    assert lines == ["Reputação (id: reputacao): 55/100", "Energia (id: energia): 80/100"]


def test_prompt_status_line_with_description_and_level_vs_without(tmp_path, monkeypatch):
    stats_yaml = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 40
  description: Quanto a escola te respeita.
  levels:
    - from: 0
      text: Você é um aluno comum.
- id: energia
  name: Energia
  min: 0
  max: 100
  default: 80
"""
    scenario, start = _load_prompt_scenario(tmp_path, monkeypatch, stats=stats_yaml)
    hud = HudState(location="patio", time="08:00", weather="clear", stats={"reputacao": 55, "energia": 80})

    prompt = build_master_prompt(scenario, start, hud, [])

    assert (
        "Reputação (id: reputacao): 55/100 — Quanto a escola te respeita. "
        "(Nível atual: Você é um aluno comum.)" in prompt
    )
    assert "Energia (id: energia): 80/100" in prompt


def test_prompt_status_section_uses_en_locale_headers(tmp_path, monkeypatch):
    stats_yaml = "- id: reputacao\n  name: Reputation\n  min: 0\n  max: 100\n  default: 55\n"
    scenario, start = _load_prompt_scenario(tmp_path, monkeypatch, locale="en", stats=stats_yaml)
    hud = HudState(location="patio", time="08:00", weather="clear", stats={"reputacao": 55})

    prompt = build_master_prompt(scenario, start, hud, [])

    assert "## PLAYER STATUS" in prompt


def test_prompt_status_section_absent_without_stats(tmp_path, monkeypatch):
    scenario, start = _load_prompt_scenario(tmp_path, monkeypatch)
    hud = HudState(location="patio", time="08:00", weather="clear")

    prompt = build_master_prompt(scenario, start, hud, [])

    assert "## STATUS DO JOGADOR" not in prompt.split("\n")


def test_prompt_status_description_multiline_yaml_block_collapses_to_one_line(tmp_path, monkeypatch):
    stats_yaml = (
        "- id: reputacao\n"
        "  name: Reputação\n"
        "  min: 0\n"
        "  max: 100\n"
        "  default: 40\n"
        "  description: |\n"
        "    Quanto a\n"
        "    escola\n"
        "    te respeita.\n"
    )
    scenario, start = _load_prompt_scenario(tmp_path, monkeypatch, stats=stats_yaml)
    hud = HudState(location="patio", time="08:00", weather="clear", stats={"reputacao": 40})

    prompt = build_master_prompt(scenario, start, hud, [])

    assert "Reputação (id: reputacao): 40/100 — Quanto a escola te respeita." in prompt
    assert "Quanto a\nescola" not in prompt


def test_format_body_mentions_stat_id_tag_in_both_locales(tmp_path, monkeypatch):
    scenario_pt, start_pt = _load_prompt_scenario(tmp_path, monkeypatch)
    hud = HudState(location="patio", time="08:00", weather="clear")
    prompt_pt = build_master_prompt(scenario_pt, start_pt, hud, [])
    assert "[STAT:id:±N]" in prompt_pt

    scenario_en, start_en = _load_prompt_scenario(tmp_path, monkeypatch, locale="en")
    prompt_en = build_master_prompt(scenario_en, start_en, hud, [])
    assert "[STAT:id:±N]" in prompt_en


# --- route integration tests --------------------------------------------------

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

DEFAULT_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
  time: "07:50"
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

STATS_YAML = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 40
"""


def _write_scenario(root, scenario_id="exemplo-escola", *, stats=None):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    if stats is not None:
        (scenario_path / "stats.yaml").write_text(stats, encoding="utf-8")

    return scenario_path


def _config():
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
        }
    )


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OOC_SESSIONS_DB", str(tmp_path / "sessions.db"))
    yield


@pytest.fixture
def scenarios_root(tmp_path, monkeypatch):
    root = tmp_path / "scenarios"
    root.mkdir()
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)
    return root


def _stream_events(response) -> list[dict]:
    events = []
    for line in "".join(response.iter_text()).splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:") :].strip()
        if payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


def _make_fake_stream(deltas, captured=None, raise_after=None):
    async def fake_stream(self, messages, model):
        if captured is not None:
            captured.append(messages)
        for i, delta in enumerate(deltas):
            if raise_after is not None and i == raise_after:
                raise RuntimeError("provider exploded")
            yield delta

    return fake_stream


def test_route_stat_tag_updates_sse_event_and_next_turn_prompt(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, stats=STATS_YAML)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce ganha respeito [STAT:reputacao:+5]."])
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        events = _stream_events(response)

    stats = events[-1]["hud"]["stats"]
    assert {s["id"]: s["value"] for s in stats} == {"reputacao": 45}

    stat_events = [e for e in sessions.read_events(session["id"]) if e.kind == "stat"]
    assert len(stat_events) == 1
    assert stat_events[0].payload == {"id": "reputacao", "delta": 5, "value": 45, "source": "tag"}

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert {s["id"]: s["value"] for s in detail["stats"]} == {"reputacao": 45}

    captured: list = []
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["ok"], captured=captured))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "segue"}
    ) as response:
        _stream_events(response)

    system_prompt = captured[0][0].content
    assert "Reputação (id: reputacao): 45/100" in system_prompt


def test_route_stat_tag_with_unknown_id_is_invalid_and_no_stat_event(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, stats=STATS_YAML)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["nada muda [STAT:fantasma:+1]."])
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        events = _stream_events(response)

    all_events = sessions.read_events(session["id"])
    tag_events = [e for e in all_events if e.kind == "tag"]
    assert tag_events[0].payload["valid"] is False
    assert [e for e in all_events if e.kind == "stat"] == []

    stats = events[-1]["hud"]["stats"]
    assert {s["id"]: s["value"] for s in stats} == {"reputacao": 40}


def test_route_two_stat_tags_same_id_same_turn_produce_two_ordered_events(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, stats=STATS_YAML)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _make_fake_stream(["primeiro [STAT:reputacao:+5]. depois [STAT:reputacao:+3]."]),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        _stream_events(response)

    stat_events = [e for e in sessions.read_events(session["id"]) if e.kind == "stat"]
    assert [e.payload for e in stat_events] == [
        {"id": "reputacao", "delta": 5, "value": 45, "source": "tag"},
        {"id": "reputacao", "delta": 3, "value": 48, "source": "tag"},
    ]


def test_route_scenario_without_stats_yaml_has_empty_hud_stats_and_no_stat_event(
    scenarios_root, monkeypatch
):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["ola mundo."]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "oi"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["stats"] == []
    assert [e for e in sessions.read_events(session["id"]) if e.kind == "stat"] == []


def test_route_legacy_session_hud_missing_stats_key_gets_defaults_after_turn(
    scenarios_root, monkeypatch
):
    _write_scenario(scenarios_root, stats=STATS_YAML)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["ola mundo."]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    conn = sessions._connect()
    try:
        conn.execute(
            "UPDATE sessions SET hud = ? WHERE id = ?",
            ('{"turn": 0, "location": "patio", "time": "07:50", "weather": "clear"}', session["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "oi"}
    ) as response:
        events = _stream_events(response)

    stats = events[-1]["hud"]["stats"]
    assert {s["id"]: s["value"] for s in stats} == {"reputacao": 40}

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["hud"]["stats"] == {"reputacao": 40}


def test_route_provider_error_mid_stream_after_valid_stat_tag_does_not_persist(
    scenarios_root, monkeypatch
):
    _write_scenario(scenarios_root, stats=STATS_YAML)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _make_fake_stream(["ganha respeito [STAT:reputacao:+5]", " mais texto"], raise_after=1),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        events = _stream_events(response)

    assert any("error" in e for e in events)
    assert sessions.read_events(session["id"]) == []
