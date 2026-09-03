import json

import pytest
from fastapi.testclient import TestClient

from app import main, sessions, turn
from app.config import Config
from app.llm.openai_compat import OpenAICompatProvider

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
allow_dynamic_stats: {allow_dynamic_stats}
"""

DEFAULT_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
  time: "07:50"
characters: [chloe]
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


def _write_scenario(root, scenario_id="exemplo-escola", *, allow_dynamic_stats=False, stats=STATS_YAML):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    scenario_path.joinpath("scenario.yaml").write_text(
        SCENARIO_YAML.format(allow_dynamic_stats=str(allow_dynamic_stats).lower()), encoding="utf-8"
    )
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


def _config(flags=None, allow_dynamic_stats=False):
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {
                "narrator": {"provider": "local", "model": "narrator-model"},
                "utility": {"provider": "local", "model": "utility-model"},
            },
            "flags": {"director": False, **(flags or {})},
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


def _setup(scenarios_root, monkeypatch, *, flags=None, allow_dynamic_stats=False, stats=STATS_YAML):
    _write_scenario(scenarios_root, allow_dynamic_stats=allow_dynamic_stats, stats=stats)
    config = _config(flags, allow_dynamic_stats)
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(turn, "load_config", lambda: config)
    return TestClient(main.app)


def _route_by_model(narrator_deltas, utility_reply):
    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield utility_reply
        else:
            for delta in narrator_deltas:
                yield delta

    return fake_stream


def _turn(client, session_id, message="continua"):
    with client.stream(
        "POST", f"/api/sessions/{session_id}/turn", json={"message": message}
    ) as response:
        return _stream_events(response)


def test_judge_applies_stat_delta(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route_by_model(["voce conversa com a Chloe."], '{"stats": {"reputacao": -5}}'),
    )
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    events = _turn(client, session["id"])

    stat_view = next(s for s in events[-1]["hud"]["stats"] if s["id"] == "reputacao")
    assert stat_view["value"] == 35

    stat_events = [e for e in sessions.read_events(session["id"]) if e.kind == "stat"]
    assert len(stat_events) == 1
    assert stat_events[0].payload["source"] == "judge"
    assert stat_events[0].payload["value"] == 35

    applied = [props for name, props in emitted if name == "judge_applied"]
    assert len(applied) == 1
    assert applied[0]["changes"] == [{"id": "reputacao", "delta": -5, "value": 35}]
    assert isinstance(applied[0]["duration_ms"], int)


def test_tag_precedence_over_judge_on_same_stat(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route_by_model(
            ["voce se esforça. [STAT:reputacao:+3]"], '{"stats": {"reputacao": -5}}'
        ),
    )
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    events = _turn(client, session["id"])

    stat_view = next(s for s in events[-1]["hud"]["stats"] if s["id"] == "reputacao")
    assert stat_view["value"] == 43

    stat_events = [e for e in sessions.read_events(session["id"]) if e.kind == "stat"]
    assert len(stat_events) == 1
    assert stat_events[0].payload["source"] == "tag"

    applied = [props for name, props in emitted if name == "judge_applied"]
    assert len(applied) == 1
    assert applied[0]["changes"] == []
    assert applied[0]["rejected"] == [{"id": "reputacao", "reason": "touched_by_tag"}]


def test_judge_creates_dynamic_stat_when_allowed(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, allow_dynamic_stats=True)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route_by_model(
            ["voce encontra um item."],
            '{"new": [{"id": "vida", "name": "Vida", "value": 110, "max": 110}]}',
        ),
    )

    events = _turn(client, session["id"])

    stats = events[-1]["hud"]["stats"]
    assert stats[-1]["id"] == "vida"
    assert stats[-1]["value"] == 110

    stat_events = [e for e in sessions.read_events(session["id"]) if e.kind == "stat"]
    assert len(stat_events) == 1
    assert stat_events[0].payload["source"] == "judge"
    assert stat_events[0].payload["value"] == 110


def test_dynamic_stat_disabled_by_default_is_rejected(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, allow_dynamic_stats=False)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route_by_model(
            ["voce encontra um item."],
            '{"new": [{"id": "vida", "name": "Vida", "value": 110, "max": 110}]}',
        ),
    )
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    events = _turn(client, session["id"])

    stats = events[-1]["hud"]["stats"]
    assert all(s["id"] != "vida" for s in stats)

    applied = [props for name, props in emitted if name == "judge_applied"]
    assert applied[0]["rejected"] == [{"id": "new", "reason": "dynamic_disabled"}]


def test_minds_applied_reflected_in_sse_and_get_session(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route_by_model(
            ["voce encara a Chloe."],
            '{"chloe": {"attitude": "desconfiada", "emoji": "\U0001f928", "event": "te viu"}}',
        ),
    )
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    events = _turn(client, session["id"])

    assert events[-1]["hud"]["minds"]["chloe"]["attitude"] == "desconfiada"

    minds_events = [e for e in sessions.read_events(session["id"]) if e.kind == "minds"]
    assert len(minds_events) == 1
    assert minds_events[0].payload["entries"]["chloe"]["attitude"] == "desconfiada"

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["minds"]["chloe"]["attitude"] == "desconfiada"

    applied = [props for name, props in emitted if name == "minds_applied"]
    assert len(applied) == 1
    assert applied[0]["changed"] == ["chloe"]


def test_next_turn_prompt_carries_current_state(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    captured_narrator = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"chloe": {"attitude": "desconfiada", "emoji": "\U0001f928", "event": "te viu"}}'
        else:
            captured_narrator.append(messages)
            yield "voce encara a Chloe."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    _turn(client, session["id"])
    _turn(client, session["id"], message="continua")

    second_turn_system = captured_narrator[1][0].content
    assert "Estado atual: desconfiada" in second_turn_system


def test_minds_identical_to_previous_writes_no_new_event(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"chloe": {"attitude": "desconfiada", "emoji": "\U0001f928", "event": "te viu"}}'
        else:
            yield "voce encara a Chloe."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    _turn(client, session["id"])
    _turn(client, session["id"], message="continua")

    minds_events = [e for e in sessions.read_events(session["id"]) if e.kind == "minds"]
    assert len(minds_events) == 1


def test_flags_disabled_no_utility_call(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, flags={"hud_judge": False, "minds": False})
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield '{"stats": {"reputacao": -5}}'
        else:
            yield "voce continua."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    events = _turn(client, session["id"])

    assert utility_calls == []
    stat_view = next(s for s in events[-1]["hud"]["stats"] if s["id"] == "reputacao")
    assert stat_view["value"] == 40
    assert events[-1]["hud"]["minds"] == {}

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["hud"]["turn"] == 1


def test_provider_error_emits_failed_for_both(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            raise RuntimeError("provider exploded")
        yield "voce continua."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    events = _turn(client, session["id"])

    assert events[-1]["hud"]["turn"] == 1
    assert len([props for name, props in emitted if name == "judge_failed"]) == 1
    assert len([props for name, props in emitted if name == "minds_failed"]) == 1


def test_invalid_json_from_utility_emits_rejected_with_truncated_raw(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, flags={"minds": False})
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    long_prose = "isso nao e json " * 20

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield long_prose
        else:
            yield "voce continua."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    _turn(client, session["id"])

    rejected = [props for name, props in emitted if name == "judge_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "invalid_json"
    from app.judge import JUDGE_RAW_LOG_CHARS

    assert rejected[0]["raw"] == long_prose[:JUDGE_RAW_LOG_CHARS]


def test_narrator_failure_after_judge_success_persists_no_events(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"stats": {"reputacao": -5}}'
        else:
            raise RuntimeError("narrator exploded")
            yield ""  # pragma: no cover

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "continua"}
    ) as response:
        assert response.status_code == 200
        _stream_events(response)

    assert sessions.read_events(session["id"]) == []


def test_corrupted_minds_event_falls_back_to_empty_map(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()
    session_id = session["id"]

    sessions.append_events(session_id, [("minds", {"entries": "lixo"})])

    response = client.get(f"/api/sessions/{session_id}")
    assert response.status_code == 200
    assert response.json()["minds"] == {}


def test_judge_stat_event_carries_dynamic_definition():
    from app.hud import DynamicStat, HudState
    from app.judge import StatChange
    from app.turn import _judge_stat_event

    hud = HudState(
        turn=1,
        location="patio",
        time="08:00",
        weather="clear",
        stats={"reputacao": 40},
        dynamic_stats={"confianca": DynamicStat(name="Confiança", value=10, min=0, max=20)},
    )

    _, dynamic_payload = _judge_stat_event(hud, StatChange(id="confianca", delta=0, value=10, source="judge"))
    _, declared_payload = _judge_stat_event(hud, StatChange(id="reputacao", delta=3, value=43, source="judge"))

    dynamic_kind = dynamic_payload.pop("kind", None)
    assert dynamic_payload == {"id": "confianca", "delta": 0, "value": 10, "source": "judge",
                               "name": "Confiança", "min": 0, "max": 20}
    assert dynamic_kind == getattr(hud.dynamic_stats["confianca"], "kind", None)
    assert declared_payload == {"id": "reputacao", "delta": 3, "value": 43, "source": "judge"}
