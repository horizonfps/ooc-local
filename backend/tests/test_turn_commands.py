import json

import pytest
from fastapi.testclient import TestClient

from app import main, sessions, turn
from app.config import Config
from app.llm.openai_compat import OpenAICompatProvider

WORLD_MD = "# Mundo\n\nUma escola nas montanhas.\n"

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

COMMANDS_YAML = """\
- name: fofoca
  description: espalha uma fofoca
  prompt: espalhe uma fofoca sobre o personagem atual
"""


def _write_scenario(root, scenario_id="exemplo-escola", *, commands=COMMANDS_YAML):
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

    if commands is not None:
        (scenario_path / "commands.yaml").write_text(commands, encoding="utf-8")

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


@pytest.fixture(autouse=True)
def _isolated_global_commands(tmp_path, monkeypatch):
    monkeypatch.setenv("OOC_COMMANDS_FILE", str(tmp_path / "global-commands.yaml"))
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


def _make_fake_stream(deltas, captured=None):
    async def fake_stream(self, messages, model):
        if captured is not None:
            captured.append(messages)
        for delta in deltas:
            yield delta

    return fake_stream


def test_scenario_command_records_meta_pair_and_hud_turn_unchanged(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Chloe anda fofocando."]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        assert response.status_code == 200
        events = _stream_events(response)

    assert events[-1]["hud"]["turn"] == 0

    stored = sessions.read_events(session["id"])
    assert [e.kind for e in stored] == ["meta_player_turn", "meta_narrator_turn"]
    assert stored[0].payload == {"text": "!fofoca", "command": "fofoca"}
    assert stored[1].payload == {"text": "Chloe anda fofocando."}


def test_scenario_command_system_prompt_matches_normal_turn(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["Chloe fofoca."], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        _stream_events(response)

    messages = captured[0]
    assert "## PERSONAGENS EM CENA" in messages[0].content
    assert messages[-1].content == (
        "Responda fora da narrativa, sem avançar a história, sem tag e sem fala de "
        "personagem em cena. Este pedido não é uma ação do jogador.\n\n"
        "espalhe uma fofoca sobre o personagem atual"
    )


def test_global_command_diary_resolves_and_records_command_name(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, commands=None)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Querido diario..."]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "/diary"}
    ) as response:
        assert response.status_code == 200
        _stream_events(response)

    stored = sessions.read_events(session["id"])
    assert stored[0].payload["command"] == "diary"


def test_get_session_shows_meta_turns_with_meta_true_and_current_index(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Chloe fofoca."]))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        _stream_events(response)

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert len(detail["turns"]) == 2
    for turn_view in detail["turns"]:
        assert turn_view["meta"] is True
        assert turn_view["command"] == "fofoca"
        assert turn_view["index"] == 0


def test_session_detail_commands_lists_scenario_before_global(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    client = TestClient(main.app)

    detail = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    scopes = [c["scope"] for c in detail["commands"]]
    names = [c["name"] for c in detail["commands"]]
    assert scopes[0] == "scenario"
    assert names[0] == "fofoca"
    assert scopes[1:] == ["global"] * (len(scopes) - 1)


def test_normal_turn_between_two_metas_windows_only_first_pair(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["primeira resposta"]))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "primeiro turno"}
    ) as response:
        _stream_events(response)

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Chloe fofoca."]))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        _stream_events(response)

    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["terceira resposta"], captured=captured)
    )
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "terceiro turno"}
    ) as response:
        _stream_events(response)

    messages = captured[0]
    roles_contents = [(m.role, m.content) for m in messages]
    assert ("user", "primeiro turno") in roles_contents
    assert ("assistant", "primeira resposta") in roles_contents
    assert not any("fofoca" in content for _, content in roles_contents if content)
    assert not any("Chloe fofoca." in content for _, content in roles_contents if content)


def test_turn_count_does_not_count_meta(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Chloe fofoca."]))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        _stream_events(response)

    summary = next(s for s in client.get("/api/sessions").json() if s["id"] == session["id"])
    assert summary["turnCount"] == 0


def test_two_metas_in_a_row_share_index(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Chloe fofoca 1."]))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        _stream_events(response)

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Chloe fofoca 2."]))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        _stream_events(response)

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert len(detail["turns"]) == 4
    assert all(t["meta"] for t in detail["turns"])
    assert all(t["index"] == 0 for t in detail["turns"])


def test_message_with_slash_inside_but_not_leading_runs_as_normal_turn(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Voce diz isso."]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "vou ver /diary depois"}
    ) as response:
        assert response.status_code == 200
        events = _stream_events(response)

    assert events[-1]["hud"]["turn"] == 1
    stored = sessions.read_events(session["id"])
    assert [e.kind for e in stored] == ["player_turn", "narrator_turn"]


def test_unknown_scenario_command_is_422_and_nothing_recorded(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    emitted = []
    monkeypatch.setattr(main, "emit", lambda event, **props: emitted.append((event, props)))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    response = client.post(f"/api/sessions/{session['id']}/turn", json={"message": "!naoexiste"})

    assert response.status_code == 422
    assert response.json() == {"detail": "unknown_command"}
    assert sessions.read_events(session["id"]) == []
    rejected = [props for name, props in emitted if name == "turn_rejected"]
    assert len(rejected) == 1
    assert rejected[0]["reason"] == "unknown_command"


def test_unknown_global_command_is_422(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    response = client.post(f"/api/sessions/{session['id']}/turn", json={"message": "/naoexiste"})

    assert response.status_code == 422
    assert response.json() == {"detail": "unknown_command"}


def test_meta_turn_empty_narrator_text_errors_without_recording(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["   "]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        events = _stream_events(response)

    assert any("error" in e for e in events)
    assert sessions.read_events(session["id"]) == []
