import sqlite3
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


def test_init_db_purges_ephemeral_and_keeps_normal(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    normal = sessions.create_session("exemplo-escola")
    ephemeral = sessions.create_session("exemplo-escola", ephemeral=True)

    sessions.init_db()
    sessions.init_db()

    assert [s.id for s in sessions.list_sessions()] == [normal.id]
    with pytest.raises(sessions.SessionNotFound):
        sessions.get_session(ephemeral.id)


def test_init_db_migrates_db_missing_ephemeral_column(tmp_path, monkeypatch, scenarios_root):
    db_file = tmp_path / "legacy.db"
    monkeypatch.setenv("OOC_SESSIONS_DB", str(db_file))

    conn = sqlite3.connect(db_file)
    conn.executescript(
        """
        CREATE TABLE sessions (
          id            TEXT PRIMARY KEY,
          scenario_id   TEXT NOT NULL,
          scenario_name TEXT NOT NULL,
          start_id      TEXT NOT NULL,
          created_at    TEXT NOT NULL,
          updated_at    TEXT NOT NULL,
          hud           TEXT NOT NULL,
          compact       TEXT,
          compact_seq   INTEGER
        );
        CREATE TABLE events (
          id         INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL REFERENCES sessions(id),
          seq        INTEGER NOT NULL,
          kind       TEXT NOT NULL,
          payload    TEXT NOT NULL,
          created_at TEXT NOT NULL,
          UNIQUE(session_id, seq)
        );
        """
    )
    conn.execute(
        "INSERT INTO sessions (id, scenario_id, scenario_name, start_id, created_at, updated_at, hud) "
        "VALUES ('legacy-id', 'exemplo-escola', 'Exemplo Escola', 'default', 't', 't', "
        "'{\"location\": \"patio\", \"turn\": 0}')"
    )
    conn.commit()
    conn.close()

    sessions.init_db()

    conn = sqlite3.connect(db_file)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    assert "ephemeral" in columns
    conn.close()

    summaries = sessions.list_sessions()
    assert [s.id for s in summaries] == ["legacy-id"]


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


def test_reopening_db_persists_ephemeral_state(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    detail = sessions.create_session("exemplo-escola", ephemeral=True)
    sessions.append_events(
        detail.id,
        [("player_turn", {"text": "oi"}), ("narrator_turn", {"text": "ola"})],
    )

    reopened = sessions.get_session(detail.id)
    assert len(reopened.turns) == 2


def test_create_session_explicit_start_ephemeral(scenarios_root):
    _write_scenario(
        scenarios_root,
        "exemplo-escola",
        starts={"default.yaml": DEFAULT_START, "rota-vilao.yaml": VILLAIN_START},
    )

    detail = sessions.create_session("exemplo-escola", "rota-vilao", ephemeral=True)

    assert detail.prologue == "prologo vilao"
    assert detail.hud.location == "sala"


def test_list_sessions_excludes_ephemeral(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    normal = sessions.create_session("exemplo-escola")
    sessions.create_session("exemplo-escola", ephemeral=True)

    summaries = sessions.list_sessions()

    assert [s.id for s in summaries] == [normal.id]


def test_get_session_reads_ephemeral_while_alive(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    ephemeral = sessions.create_session("exemplo-escola", ephemeral=True)

    reopened = sessions.get_session(ephemeral.id)

    assert reopened.id == ephemeral.id


def test_ephemeral_session_can_play_a_turn(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    ephemeral = sessions.create_session("exemplo-escola", ephemeral=True)

    sessions.append_events(
        ephemeral.id,
        [("player_turn", {"text": "eu ando"}), ("narrator_turn", {"text": "voce anda"})],
    )

    events = sessions.read_events(ephemeral.id)
    assert [e.kind for e in events] == ["player_turn", "narrator_turn"]


def test_delete_session_removes_ephemeral_and_its_events(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    ephemeral = sessions.create_session("exemplo-escola", ephemeral=True)
    sessions.append_events(
        ephemeral.id,
        [("player_turn", {"text": "eu ando"}), ("narrator_turn", {"text": "voce anda"})],
    )

    sessions.delete_session(ephemeral.id)

    assert sessions.read_events(ephemeral.id) == []
    with pytest.raises(sessions.SessionNotFound):
        sessions.get_session(ephemeral.id)


def test_delete_session_normal_raises_not_ephemeral_and_keeps_it(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    normal = sessions.create_session("exemplo-escola")

    with pytest.raises(sessions.SessionNotEphemeral):
        sessions.delete_session(normal.id)

    assert [s.id for s in sessions.list_sessions()] == [normal.id]


def test_delete_session_not_found():
    with pytest.raises(sessions.SessionNotFound):
        sessions.delete_session("does-not-exist")


def test_delete_session_rollback_on_sqlite_error(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, "exemplo-escola")
    ephemeral = sessions.create_session("exemplo-escola", ephemeral=True)
    sessions.append_events(
        ephemeral.id,
        [("player_turn", {"text": "eu ando"}), ("narrator_turn", {"text": "voce anda"})],
    )

    real_connect = sessions._connect

    class FailingConnection:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args, **kwargs):
            if sql.startswith("DELETE FROM sessions"):
                raise sqlite3.OperationalError("boom")
            return self._conn.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    monkeypatch.setattr(sessions, "_connect", lambda: FailingConnection(real_connect()))

    with pytest.raises(sqlite3.OperationalError):
        sessions.delete_session(ephemeral.id)

    monkeypatch.setattr(sessions, "_connect", real_connect)

    reopened = sessions.get_session(ephemeral.id)
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


def test_delete_sessions_route_ephemeral_happy_path(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    client = TestClient(main.app)
    created = client.post("/api/sessions", json={"scenarioId": "exemplo-escola", "ephemeral": True})
    session_id = created.json()["id"]

    response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"/api/sessions/{session_id}").status_code == 404


def test_delete_sessions_route_normal_is_409(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    client = TestClient(main.app)
    created = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"})
    session_id = created.json()["id"]

    response = client.delete(f"/api/sessions/{session_id}")

    assert response.status_code == 409
    assert response.json() == {"detail": "session is not ephemeral"}
    assert client.get(f"/api/sessions/{session_id}").status_code == 200


def test_delete_sessions_route_not_found_is_404(scenarios_root):
    client = TestClient(main.app)
    response = client.delete("/api/sessions/does-not-exist")
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
