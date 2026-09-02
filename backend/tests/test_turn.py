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


def test_turn_happy_path_emits_deltas_hud_then_done(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["voce anda", " ate a Chloe."])
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "vou ate a Chloe"}
    ) as response:
        assert response.status_code == 200
        events = _stream_events(response)

    assert events[0] == {"delta": "voce anda"}
    assert events[1] == {"delta": " ate a Chloe."}
    assert events[-1]["hud"]["turn"] == 1
    assert "dynamic_stats" not in events[-1]["hud"]
    assert not isinstance(events[-1]["hud"].get("stats"), dict)

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert len(detail["turns"]) == 2
    assert detail["turns"][0]["text"] == "vou ate a Chloe"
    assert detail["turns"][1]["text"] == "voce anda ate a Chloe."
    assert detail["hud"]["turn"] == 1


def test_turn_records_tags_as_events(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, stats=STATS_YAML)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _make_fake_stream(["voce se sente melhor [STAT:reputacao:+1]."]),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        _stream_events(response)

    events = sessions.read_events(session["id"])
    tag_events = [e for e in events if e.kind == "tag"]
    assert len(tag_events) == 1
    assert tag_events[0].payload == {"kind": "STAT", "args": ["reputacao", "+1"], "raw": "[STAT:reputacao:+1]", "valid": True}

    narrator_event = next(e for e in events if e.kind == "narrator_turn")
    assert narrator_event.payload["text"] == "voce se sente melhor."


def test_turn_strips_hud_echo_and_keeps_tag_events(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _make_fake_stream(
            ["# Turno 1\nLocal: patio\nVoce anda ate a Chloe. [STAT:reputacao:+1]"]
        ),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        _stream_events(response)

    events = sessions.read_events(session["id"])
    narrator_event = next(e for e in events if e.kind == "narrator_turn")
    assert narrator_event.payload["text"] == "Voce anda ate a Chloe."
    tag_events = [e for e in events if e.kind == "tag"]
    assert len(tag_events) == 1


def test_turn_that_is_only_hud_and_player_echo_is_treated_as_failure(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["# Turno 1\n**Você** | ando"])
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        events = _stream_events(response)

    assert any("error" in e for e in events)
    assert all("hud" not in e for e in events)
    assert sessions.read_events(session["id"]) == []


def test_turn_second_turn_includes_previous_pair_in_context(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["primeira resposta"]))
    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "primeira mensagem"}
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
    assert ("user", "primeira mensagem") in roles_contents
    assert ("assistant", "primeira resposta") in roles_contents
    assert ("user", "segunda mensagem") in roles_contents


def test_turn_that_is_only_a_tag_is_treated_as_failure(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["[STAT:reputacao:+1]"]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        events = _stream_events(response)

    assert any("error" in e for e in events)
    assert all("hud" not in e for e in events)
    assert sessions.read_events(session["id"]) == []


def test_turn_window_truncated_at_18_pairs(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    events = []
    for i in range(25):
        events.append(("player_turn", {"text": f"jogador {i}"}))
        events.append(("narrator_turn", {"text": f"narrador {i}"}))
    sessions.append_events(session["id"], events)

    messages = turn.build_context(session["id"], "nova mensagem")
    non_system_non_new = messages[1:-1]
    assert len(non_system_non_new) == 36
    assert non_system_non_new[0].content == "jogador 7"


def test_turn_provider_error_mid_stream_does_not_persist(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["ola", " mundo"], raise_after=1)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    before = sessions.read_events(session["id"])

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        events = _stream_events(response)

    assert events[0] == {"delta": "ola"}
    assert any("error" in e for e in events)
    assert all("hud" not in e for e in events)

    after = sessions.read_events(session["id"])
    assert before == after == []


def test_turn_append_events_failure_preserves_hud(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["ola mundo"]))

    def boom(*args, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(turn, "append_events", boom)
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ajudo"}
    ) as response:
        events = _stream_events(response)

    assert any("error" in e for e in events)
    assert all("hud" not in e for e in events)

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["hud"]["turn"] == 0


def test_turn_route_flag_disabled_is_503(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(
        main,
        "load_config",
        lambda: Config.model_validate(
            {
                "providers": {"local": {"base_url": "http://x/v1"}},
                "models": {"narrator": {"provider": "local", "model": "m"}},
                "flags": {"chat": False},
            }
        ),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    response = client.post(f"/api/sessions/{session['id']}/turn", json={"message": "oi"})
    assert response.status_code == 503


def test_turn_route_session_not_found_is_404(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    client = TestClient(main.app)

    response = client.post("/api/sessions/nao-existe/turn", json={"message": "oi"})
    assert response.status_code == 404
    assert response.json() == {"detail": "session not found"}


def test_turn_route_scenario_deleted_is_404(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    empty_root = scenarios_root.parent / "empty-scenarios"
    empty_root.mkdir()
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: empty_root)

    response = client.post(f"/api/sessions/{session['id']}/turn", json={"message": "oi"})
    assert response.status_code == 404
    assert response.json() == {"detail": "scenario not found"}


def test_turn_full_turn_reads_scenario_and_session_row_exactly_once(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["ola"]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    real_get_session_row = turn.get_session_row
    real_load_scenario = turn.load_scenario
    session_row_calls = []
    scenario_calls = []

    def counting_get_session_row(session_id):
        session_row_calls.append(session_id)
        return real_get_session_row(session_id)

    def counting_load_scenario(scenario_id):
        scenario_calls.append(scenario_id)
        return real_load_scenario(scenario_id)

    monkeypatch.setattr(turn, "get_session_row", counting_get_session_row)
    monkeypatch.setattr(turn, "load_scenario", counting_load_scenario)

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "oi"}
    ) as response:
        _stream_events(response)

    assert len(session_row_calls) == 1
    assert len(scenario_calls) == 1


def test_turn_system_prompt_contains_world_characters_and_hud(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    captured: list = []
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["ola"], captured=captured)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "oi"}
    ) as response:
        _stream_events(response)

    system_prompt = captured[0][0].content
    assert "Uma escola" in system_prompt
    assert "Chloe" in system_prompt
    assert "## ESTADO DO JOGO" in system_prompt
    assert "Turno: 0" in system_prompt


def test_turn_route_missing_narrator_role_emits_turn_failed_and_done(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    config_without_narrator = Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"utility": {"provider": "local", "model": "m"}},
            "flags": {"director": False},
        }
    )
    monkeypatch.setattr(main, "load_config", lambda: config_without_narrator)
    emitted = []
    monkeypatch.setattr(main, "emit", lambda event, **props: emitted.append((event, props)))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "oi"}
    ) as response:
        assert response.status_code == 200
        events = _stream_events(response)

    assert events == [{"error": "turn_failed"}]
    failed = [props for name, props in emitted if name == "turn_stream_failed"]
    assert len(failed) == 1
    assert failed[0]["session_id"] == session["id"]


def test_turn_route_session_deleted_mid_stream_ends_error_and_done(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()
    session_id = session["id"]

    async def fake_stream_and_delete(self, messages, model):
        import sqlite3

        conn = sqlite3.connect(sessions.db_path())
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()
        yield "ola"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream_and_delete)

    with client.stream(
        "POST", f"/api/sessions/{session_id}/turn", json={"message": "oi"}
    ) as response:
        assert response.status_code == 200
        events = _stream_events(response)

    assert events[0] == {"delta": "ola"}
    assert events[-1] == {"error": "turn_failed"}
    assert all("hud" not in e for e in events)
    assert sessions.read_events(session_id) == []


def test_turn_route_missing_session_with_empty_message_is_404(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    client = TestClient(main.app)

    response = client.post("/api/sessions/nao-existe/turn", json={"message": "   "})
    assert response.status_code == 404
    assert response.json() == {"detail": "session not found"}


def test_turn_provider_error_sanitizes_message_to_turn_failed(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream(["ola", " mundo"], raise_after=1)
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "oi"}
    ) as response:
        events = _stream_events(response)

    assert events[-1] == {"error": "turn_failed"}
    assert not any("provider exploded" in json.dumps(e) for e in events)


def test_turn_route_empty_message_is_422(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    response = client.post(f"/api/sessions/{session['id']}/turn", json={"message": "   "})
    assert response.status_code == 422
    assert response.json() == {"detail": "message must not be empty"}


def test_advance_increments_turn_and_time():
    from app.hud import HudState, advance

    hud = HudState(turn=0, location="patio", time="07:50", weather="clear")
    advanced = advance(hud)
    assert advanced.turn == 1
    assert advanced.time == "07:52"


def test_advance_wraps_midnight():
    from app.hud import HudState, advance

    hud = HudState(turn=5, location="patio", time="23:59", weather="clear")
    advanced = advance(hud)
    assert advanced.time == "00:01"


def test_apply_location_normalizes_and_updates():
    from app.hud import HudState, apply_location

    hud = HudState(turn=0, location="patio", time="07:50", weather="clear")
    updated = apply_location(hud, "  pátio   da   escola  ")
    assert updated.location == "pátio da escola"


def test_apply_location_same_value_returns_same_hud():
    from app.hud import HudState, apply_location

    hud = HudState(turn=0, location="patio", time="07:50", weather="clear")
    updated = apply_location(hud, "patio")
    assert updated is hud


def test_apply_location_empty_after_normalization_keeps_hud():
    from app.hud import HudState, apply_location

    hud = HudState(turn=0, location="patio", time="07:50", weather="clear")
    updated = apply_location(hud, "   ")
    assert updated is hud


def test_apply_location_truncates_at_word_boundary():
    from app.hud import LOCATION_MAX_CHARS, HudState, apply_location

    hud = HudState(turn=0, location="patio", time="07:50", weather="clear")

    no_spaces = "a" * 200
    updated_no_spaces = apply_location(hud, no_spaces)
    assert updated_no_spaces.location == "a" * LOCATION_MAX_CHARS

    words = "sala de aula do terceiro ano do ensino fundamental do bairro novo"
    updated_words = apply_location(hud, words)
    assert len(updated_words.location) <= LOCATION_MAX_CHARS
    assert words.startswith(updated_words.location)
    cut_at = len(updated_words.location)
    assert cut_at == len(words) or words[cut_at] == " "


def test_turn_applies_loc_tag_to_hud(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _make_fake_stream(["Voce sobe a escada. [LOC:sala do 3 B]"]),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu subo"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["location"] == "sala do 3 B"

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["hud"]["location"] == "sala do 3 B"


def test_turn_without_loc_tag_preserves_previous_location(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(["Voce anda."]))
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ando"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["location"] == "patio"


def test_turn_last_loc_tag_wins(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _make_fake_stream(["Voce anda. [LOC:corredor] Voce entra. [LOC:sala do 3 B]"]),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ando"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["location"] == "sala do 3 B"


def test_turn_invalid_loc_tag_does_not_change_hud(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn, "load_config", lambda: _config())
    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _make_fake_stream(["Voce anda. [LOC:sala 3: fundo]"]),
    )
    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu ando"}
    ) as response:
        events = _stream_events(response)

    assert events[-1]["hud"]["location"] == "patio"

    tag_events = [e for e in sessions.read_events(session["id"]) if e.kind == "tag"]
    assert len(tag_events) == 1
    assert tag_events[0].payload["kind"] == "LOC"
    assert tag_events[0].payload["valid"] is False
    assert tag_events[0].payload["args"] == ["sala 3", "fundo"]
