from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from app import main
from app import sessions

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
play_guide: guia default
hud:
  location: patio
"""

VILLAIN_START = """\
name: Rota vilão
prologue: prologo vilao
opening_scene: cena2
hud:
  location: sala
  time: "20:00"
  weather: storm
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


def _write_scenario(root, scenario_id, *, starts=None):
    starts = {"default.yaml": DEFAULT_START} if starts is None else starts

    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    for filename, content in starts.items():
        (starts_dir / filename).write_text(content, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    return scenario_path


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


def test_init_db_is_idempotent():
    sessions.init_db()
    sessions.init_db()


def test_create_session_happy_path(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    detail = sessions.create_session("exemplo-escola")

    assert detail.turns == []
    assert detail.prologue == "prologo default"
    assert detail.hud.turn == 0
    assert detail.hud.location == "patio"


def test_create_session_scenario_not_found(scenarios_root):
    with pytest.raises(sessions.ScenarioNotFound):
        sessions.create_session("nao-existe")


def test_create_session_start_not_found(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    with pytest.raises(sessions.StartNotFound):
        sessions.create_session("exemplo-escola", "nao-existe")


def test_create_session_explicit_start(scenarios_root):
    _write_scenario(
        scenarios_root,
        "exemplo-escola",
        starts={"default.yaml": DEFAULT_START, "rota-vilao.yaml": VILLAIN_START},
    )

    detail = sessions.create_session("exemplo-escola", "rota-vilao")

    assert detail.prologue == "prologo vilao"
    assert detail.hud.location == "sala"


def test_list_sessions_orders_by_updated_at_desc(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    first = sessions.create_session("exemplo-escola")
    second = sessions.create_session("exemplo-escola")

    summaries = sessions.list_sessions()

    assert [s.id for s in summaries] == [second.id, first.id]
    assert all(s.turn_count == 0 for s in summaries)


def test_list_sessions_empty_returns_empty_list():
    assert sessions.list_sessions() == []


def test_append_events_creates_turn_pair(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        [("player_turn", {"text": "eu ando"}), ("narrator_turn", {"text": "voce anda"})],
    )

    reopened = sessions.get_session(detail.id)

    assert len(reopened.turns) == 2
    assert reopened.turns[0].index == 1
    assert reopened.turns[0].role == "player"
    assert reopened.turns[0].text == "eu ando"
    assert reopened.turns[1].index == 1
    assert reopened.turns[1].role == "narrator"
    assert reopened.turns[1].text == "voce anda"


def test_append_events_updates_hud_and_updated_at(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")
    new_hud = detail.hud.model_copy(update={"turn": 1, "location": "sala"})

    sessions.append_events(
        detail.id,
        [("player_turn", {"text": "oi"}), ("narrator_turn", {"text": "ola"})],
        hud=new_hud,
    )

    reopened = sessions.get_session(detail.id)
    assert reopened.hud.turn == 1
    assert reopened.hud.location == "sala"


def test_append_events_is_atomic_on_failure(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")
    original_hud = detail.hud

    class NotSerializable:
        pass

    with pytest.raises(TypeError):
        sessions.append_events(
            detail.id,
            [("player_turn", {"text": "oi"}), ("narrator_turn", {"text": NotSerializable()})],
            hud=detail.hud.model_copy(update={"turn": 99}),
        )

    reopened = sessions.get_session(detail.id)
    assert reopened.turns == []
    assert reopened.hud == original_hud


def test_get_session_not_found():
    with pytest.raises(sessions.SessionNotFound):
        sessions.get_session("does-not-exist")


def test_get_session_scenario_deleted_but_listing_still_works(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")

    empty_root = scenarios_root.parent / "empty-scenarios"
    empty_root.mkdir()
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: empty_root)

    with pytest.raises(sessions.ScenarioNotFound):
        sessions.get_session(detail.id)

    summaries = sessions.list_sessions()
    assert summaries[0].scenario_name == "Exemplo Escola"


def test_reopening_db_persists_state(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(
        detail.id,
        [("player_turn", {"text": "oi"}), ("narrator_turn", {"text": "ola"})],
    )

    reopened = sessions.get_session(detail.id)
    assert len(reopened.turns) == 2


def test_post_sessions_route_happy_path(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    client = TestClient(main.app)

    response = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"})

    assert response.status_code == 201
    body = response.json()
    assert body["turns"] == []
    assert body["prologue"] == "prologo default"
    assert body["hud"]["turn"] == 0


def test_post_sessions_route_missing_scenario_id_is_422(scenarios_root):
    client = TestClient(main.app)
    response = client.post("/api/sessions", json={})
    assert response.status_code == 422


def test_post_sessions_route_scenario_not_found_is_404(scenarios_root):
    client = TestClient(main.app)
    response = client.post("/api/sessions", json={"scenarioId": "nao-existe"})
    assert response.status_code == 404
    assert response.json() == {"detail": "scenario not found"}
    assert sessions.list_sessions() == []


def test_get_sessions_route_lists_camel_case(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    client = TestClient(main.app)
    client.post("/api/sessions", json={"scenarioId": "exemplo-escola"})

    response = client.get("/api/sessions")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert set(["id", "scenarioId", "scenarioName", "turnCount", "updatedAt", "location"]) <= set(body[0])


def test_get_session_route_not_found_is_404(scenarios_root):
    client = TestClient(main.app)
    response = client.get("/api/sessions/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"detail": "session not found"}


def test_append_events_then_set_compact_seq_is_contiguous(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        [
            ("player_turn", {"text": "eu ando"}),
            ("narrator_turn", {"text": "voce anda"}),
            ("player_turn", {"text": "eu paro"}),
        ],
    )
    sessions.set_compact(detail.id, "resumo", 3, {})

    events = sessions.read_events(detail.id)

    assert [e.seq for e in events] == [1, 2, 3, 4]
    assert events[3].kind == "compact"


def test_set_compact_records_covered_seq(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(
        detail.id,
        [("player_turn", {"text": "eu ando"}), ("narrator_turn", {"text": "voce anda"})],
    )

    sessions.set_compact(detail.id, "resumo", 2, {})

    text, covered_seq = sessions.get_compact(detail.id)
    assert text == "resumo"
    assert covered_seq == 2


def test_append_events_empty_list_only_updates_updated_at(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(detail.id, [])

    events = sessions.read_events(detail.id)
    reopened = sessions.get_session(detail.id)
    assert events == []
    assert reopened.hud == detail.hud


def test_append_events_concurrent_writes_serialize(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")

    def append_pair(text: str) -> None:
        sessions.append_events(
            detail.id,
            [("player_turn", {"text": text}), ("narrator_turn", {"text": text})],
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(append_pair, "a"), executor.submit(append_pair, "b")]
        for future in futures:
            future.result()

    events = sessions.read_events(detail.id)
    seqs = sorted(e.seq for e in events)
    assert seqs == [1, 2, 3, 4]
    assert len(set(seqs)) == 4


def test_append_events_rollback_happens_before_close(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")

    class NotSerializable:
        pass

    with pytest.raises(TypeError):
        sessions.append_events(
            detail.id,
            [("player_turn", {"text": "oi"}), ("narrator_turn", {"text": NotSerializable()})],
        )

    events = sessions.read_events(detail.id)
    assert events == []


def test_set_compact_is_atomic_on_failure(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(
        detail.id,
        [("player_turn", {"text": "eu ando"}), ("narrator_turn", {"text": "voce anda"})],
    )
    sessions.set_compact(detail.id, "resumo original", 2, {})

    with pytest.raises(TypeError):
        sessions.set_compact(detail.id, "resumo novo", 2, {"bad": object()})

    events = sessions.read_events(detail.id)
    text, covered_seq = sessions.get_compact(detail.id)
    assert [e.kind for e in events] == ["player_turn", "narrator_turn", "compact"]
    assert text == "resumo original"
    assert covered_seq == 2
