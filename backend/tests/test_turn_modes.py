import json

import pytest
from fastapi.testclient import TestClient

from app import main, sessions, turn
from app.config import Config
from app.llm.openai_compat import OpenAICompatProvider

WORLD_MD = "# Mundo\n\nUma escola.\n"

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


def _make_fake_stream(deltas, captured=None):
    async def fake_stream(self, messages, model):
        if captured is not None:
            captured.append(messages)
        for delta in deltas:
            yield delta

    return fake_stream


@pytest.mark.parametrize(
    "mode, locale, expected_user",
    [
        ("do", "pt-br", "(Ação) vou ate a Chloe"),
        ("say", "pt-br", '(Fala) "vou ate a Chloe"'),
        ("story", "pt-br", "(Narração) vou ate a Chloe"),
        ("do", "en", "(Action) vou ate a Chloe"),
        ("say", "en", '(Speech) "vou ate a Chloe"'),
        ("story", "en", "(Narration) vou ate a Chloe"),
    ],
)
def test_turn_mode_labels_the_user_message(scenarios_root, monkeypatch, mode, locale, expected_user):
    _write_scenario(scenarios_root, locale=locale)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["resposta"], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST",
        f"/api/sessions/{session['id']}/turn",
        json={"message": "vou ate a Chloe", "mode": mode},
    ) as response:
        _stream_events(response)

    messages = captured[0]
    assert messages[-1].content == expected_user


def test_turn_mode_is_stored_in_payload_and_text_stays_raw(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["resposta"]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "vou ate a Chloe", "mode": "do"}
    ) as response:
        _stream_events(response)

    events = sessions.read_events(session["id"])
    player_event = next(e for e in events if e.kind == "player_turn")
    assert player_event.payload == {"text": "vou ate a Chloe", "mode": "do"}


def test_turn_second_turn_sees_previous_turn_labeled_in_window(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["primeira resposta"]))
    with client.stream(
        "POST",
        f"/api/sessions/{session['id']}/turn",
        json={"message": "primeira mensagem", "mode": "say"},
    ) as response:
        _stream_events(response)

    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["segunda resposta"], captured=captured)
    )
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "segunda mensagem"}
    ) as response:
        _stream_events(response)

    messages = captured[0]
    roles_contents = [(m.role, m.content) for m in messages]
    assert ("user", '(Fala) "primeira mensagem"') in roles_contents


def test_turn_window_labels_follow_the_scenario_locale(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, locale="en")
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["first reply"]))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "first move", "mode": "do"}
    ) as response:
        _stream_events(response)

    captured: list = []
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["second reply"], captured=captured))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "second move", "mode": "do"}
    ) as response:
        _stream_events(response)

    contents = [m.content for m in captured[0] if m.role == "user"]
    assert "(Action) first move" in contents
    assert not any("(Ação)" in content for content in contents)


def test_turn_without_mode_user_is_raw_and_payload_has_no_mode_key(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["resposta"], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ando"}
    ) as response:
        _stream_events(response)

    assert captured[0][-1].content == "eu ando"
    events = sessions.read_events(session["id"])
    player_event = next(e for e in events if e.kind == "player_turn")
    assert player_event.payload == {"text": "eu ando"}
    assert "mode" not in player_event.payload


def test_turn_old_event_without_mode_stays_raw_in_window_even_with_current_mode(
    scenarios_root, monkeypatch
):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    sessions.append_events(
        session["id"],
        [
            ("player_turn", {"text": "evento antigo sem mode"}),
            ("narrator_turn", {"text": "resposta antiga"}),
        ],
    )

    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["resposta nova"], captured=captured)
    )
    with client.stream(
        "POST",
        f"/api/sessions/{session['id']}/turn",
        json={"message": "mensagem atual", "mode": "say"},
    ) as response:
        _stream_events(response)

    messages = captured[0]
    roles_contents = [(m.role, m.content) for m in messages]
    assert ("user", "evento antigo sem mode") in roles_contents


def test_turn_view_mode_is_none_for_old_event(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    sessions.append_events(
        session["id"],
        [
            ("player_turn", {"text": "evento antigo"}),
            ("narrator_turn", {"text": "resposta antiga"}),
        ],
    )

    detail = client.get(f"/api/sessions/{session['id']}").json()
    player_turn = next(t for t in detail["turns"] if t["role"] == "player")
    assert player_turn["mode"] is None


def test_turn_invalid_mode_is_422_and_persists_nothing(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    response = client.post(
        f"/api/sessions/{session['id']}/turn", json={"message": "eu grito", "mode": "gritar"}
    )

    assert response.status_code == 422
    assert sessions.read_events(session["id"]) == []
