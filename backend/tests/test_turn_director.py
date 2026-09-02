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
"""

DEFAULT_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
  time: "07:50"
characters: [chloe, dara]
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

DARA_YAML = """\
name: Dara
role: professora
appearance: alta
personality: seria
voice: firme
mind:
  feeling: cautelosa
  goal: manter a ordem
"""

RENAN_YAML = """\
name: Renan
role: aluno
appearance: magro
personality: timido
voice: baixa
mind:
  feeling: ansioso
  goal: passar despercebido
"""

IRIS_YAML = """\
name: Iris
role: bibliotecaria
appearance: media
personality: gentil
voice: suave
mind:
  feeling: tranquila
  goal: organizar a biblioteca
"""


def _write_scenario(root, scenario_id="exemplo-escola"):
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
    (characters_dir / "dara.yaml").write_text(DARA_YAML, encoding="utf-8")
    (characters_dir / "renan.yaml").write_text(RENAN_YAML, encoding="utf-8")
    (characters_dir / "iris.yaml").write_text(IRIS_YAML, encoding="utf-8")

    return scenario_path


def _config(flags=None):
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {
                "narrator": {"provider": "local", "model": "narrator-model"},
                "utility": {"provider": "local", "model": "utility-model"},
            },
            "flags": {"hud_judge": False, "minds": False, **(flags or {})},
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


def _route_by_model(deltas_by_model):
    async def fake_stream(self, messages, model):
        for delta in deltas_by_model[model]:
            yield delta

    return fake_stream


def _setup(scenarios_root, monkeypatch, flags=None):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config(flags))
    monkeypatch.setattr(turn, "load_config", lambda: _config(flags))
    return TestClient(main.app)


def test_director_applies_proposal_prompt_and_hud_reflect_new_cast(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    captured_narrator = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"scene": ["chloe", "renan"]}'
        else:
            captured_narrator.append(messages)
            yield "voce anda ate a Chloe e o Renan."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "vou ate eles"}
    ) as response:
        events = _stream_events(response)

    system_content = captured_narrator[0][0].content
    assert "### Renan" in system_content
    assert "### Dara" not in system_content

    applied = [props for name, props in emitted if name == "director_applied"]
    assert len(applied) == 1
    assert applied[0]["before"] == ["chloe", "dara"]
    assert applied[0]["after"] == ["chloe", "renan"]
    assert applied[0]["added"] == ["renan"]
    assert applied[0]["removed"] == ["dara"]
    assert applied[0]["model"] == "utility-model"
    assert isinstance(applied[0]["duration_ms"], int)
    assert events[-1]["hud"]["cast"] == [
        {"id": "chloe", "name": "Chloe"},
        {"id": "renan", "name": "Renan"},
    ]

    cast_events = [e for e in sessions.read_events(session["id"]) if e.kind == "cast"]
    assert len(cast_events) == 1
    assert cast_events[0].payload == {"ids": ["chloe", "renan"], "source": "director"}


def test_director_same_proposal_twice_writes_one_cast_event(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"scene": ["chloe", "renan"]}'
        else:
            yield "voce continua."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    for _ in range(2):
        with client.stream(
            "POST", f"/api/sessions/{session['id']}/turn", json={"message": "continua"}
        ) as response:
            _stream_events(response)

    cast_events = [e for e in sessions.read_events(session["id"]) if e.kind == "cast"]
    assert len(cast_events) == 1


def test_director_decided_cast_carries_into_next_turn_prompt(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    captured_narrator = []
    turn_n = {"value": 0}

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            if turn_n["value"] == 0:
                yield '{"scene": ["chloe", "renan"]}'
            else:
                yield '{"scene": ["chloe", "renan"]}'
        else:
            captured_narrator.append(messages)
            turn_n["value"] += 1
            yield "narrativa."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    for _ in range(2):
        with client.stream(
            "POST", f"/api/sessions/{session['id']}/turn", json={"message": "continua"}
        ) as response:
            _stream_events(response)

    second_turn_system = captured_narrator[1][0].content
    assert "Renan" in second_turn_system


def test_director_empty_scene_is_accepted(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    captured_narrator = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"scene": []}'
        else:
            captured_narrator.append(messages)
            yield "voce fica sozinho."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "vou embora"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["cast"] == []
    assert "Nenhum NPC em cena no momento." in captured_narrator[0][0].content


def test_director_rejected_proposal_keeps_previous_cast(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    emitted = []
    monkeypatch.setattr(main, "emit", lambda event, **props: emitted.append((event, props)))
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"scene": ["ghost"]}'
        else:
            yield "voce continua."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "continua"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["cast"] == [
        {"id": "chloe", "name": "Chloe"},
        {"id": "dara", "name": "Dara"},
    ]
    cast_events = [e for e in sessions.read_events(session["id"]) if e.kind == "cast"]
    assert cast_events == []

    rejected = [props for name, props in emitted if name == "director_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "unknown_ids"


def test_director_flag_disabled_never_calls_utility(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, flags={"director": False})
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield '{"scene": ["chloe"]}'
        else:
            yield "voce continua."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "continua"}
    ) as response:
        events = _stream_events(response)

    assert utility_calls == []
    assert events[-1]["hud"]["cast"] == [
        {"id": "chloe", "name": "Chloe"},
        {"id": "dara", "name": "Dara"},
    ]


def test_director_provider_error_falls_back_and_narrates(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            raise RuntimeError("provider exploded")
        yield "voce continua."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "continua"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["turn"] == 1
    failed = [props for name, props in emitted if name == "director_failed"]
    assert len(failed) == 1


def test_narrator_failure_after_successful_director_persists_no_events(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"scene": ["chloe", "renan"]}'
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


def test_load_turn_context_failure_still_emits_game_turn_with_cast_none(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    with pytest.raises(Exception):
        import asyncio

        async def _drain():
            async for _ in turn.run_turn("does-not-exist", "oi"):
                pass

        asyncio.run(_drain())

    game_turns = [props for name, props in emitted if name == "game_turn"]
    assert len(game_turns) == 1
    assert game_turns[0]["cast"] is None


def test_ephemeral_session_delete_removes_cast_event_too(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post(
        "/api/sessions", json={"scenarioId": "exemplo-escola", "ephemeral": True}
    ).json()
    session_id = session["id"]

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"scene": ["chloe", "renan"]}'
        else:
            yield "voce continua."

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    with client.stream(
        "POST", f"/api/sessions/{session_id}/turn", json={"message": "continua"}
    ) as response:
        _stream_events(response)

    cast_events = [e for e in sessions.read_events(session_id) if e.kind == "cast"]
    assert len(cast_events) == 1

    delete_response = client.delete(f"/api/sessions/{session_id}")
    assert delete_response.status_code in (200, 204)
    assert sessions.read_events(session_id) == []
