from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.config import CONFIG_DIR
from app.hud import HudState, hud_from_start
from app.media import SessionAssets, session_assets
from app.observability import emit
from app.scenario import ScenarioError, load_scenario

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
  id            TEXT PRIMARY KEY,
  scenario_id   TEXT NOT NULL,
  scenario_name TEXT NOT NULL,
  start_id      TEXT NOT NULL,
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  hud           TEXT NOT NULL,
  compact       TEXT,
  compact_seq   INTEGER,
  ephemeral     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(id),
  seq        INTEGER NOT NULL,
  kind       TEXT NOT NULL,
  payload    TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(session_id, seq)
);
CREATE INDEX IF NOT EXISTS events_session_seq ON events(session_id, seq);
"""

NewEvent = tuple[str, dict]


class SessionNotFound(Exception):
    pass


class SessionNotEphemeral(Exception):
    pass


class ScenarioNotFound(Exception):
    pass


class StartNotFound(Exception):
    pass


class TurnView(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    index: int
    role: Literal["player", "narrator"]
    text: str


class SessionSummary(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    scenario_id: str = Field(alias="scenarioId")
    scenario_name: str = Field(alias="scenarioName")
    turn_count: int = Field(alias="turnCount")
    updated_at: str = Field(alias="updatedAt")
    location: str


class SessionDetail(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    scenario_id: str = Field(alias="scenarioId")
    scenario_name: str = Field(alias="scenarioName")
    prologue: str
    play_guide: str | None = Field(alias="playGuide")
    turns: list[TurnView]
    hud: HudState
    assets: SessionAssets


class SessionRow(BaseModel):
    id: str
    scenario_id: str
    start_id: str
    hud: HudState


class Event(BaseModel):
    id: int
    seq: int
    kind: str
    payload: dict
    created_at: str


def db_path() -> Path:
    env_path = os.environ.get("OOC_SESSIONS_DB")
    if env_path:
        return Path(env_path)
    return CONFIG_DIR / "sessions.db"


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA_SQL)
    return conn


def _migrate_session_columns(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(sessions)")}
    if "compact" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN compact TEXT")
    if "compact_seq" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN compact_seq INTEGER")
    if "ephemeral" not in columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN ephemeral INTEGER NOT NULL DEFAULT 0")
    conn.commit()


def init_db() -> None:
    conn = _connect()
    try:
        _migrate_session_columns(conn)
    finally:
        conn.close()
    purge_ephemeral_sessions()


def _emit_session_assets(session_id: str, assets: SessionAssets) -> None:
    emit(
        "session_assets",
        session_id=session_id,
        sprite_characters=len(assets.sprites),
        sprite_files=sum(len(emotions) for emotions in assets.sprites.values()),
        backgrounds=len(assets.backgrounds),
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def create_session(
    scenario_id: str, start_id: str | None = None, ephemeral: bool = False
) -> SessionDetail:
    try:
        scenario = load_scenario(scenario_id)
    except ScenarioError:
        raise ScenarioNotFound(scenario_id) from None
    try:
        start = scenario.start(start_id)
    except ScenarioError:
        raise StartNotFound(start_id or scenario.meta.default_start) from None

    hud = hud_from_start(start)
    session_id = uuid.uuid4().hex
    now = _now_iso()

    conn = _connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO sessions "
                "(id, scenario_id, scenario_name, start_id, created_at, updated_at, hud, ephemeral) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    scenario_id,
                    scenario.meta.name,
                    start.id,
                    now,
                    now,
                    hud.model_dump_json(),
                    int(ephemeral),
                ),
            )
    except sqlite3.Error as exc:
        emit("session_db_error", op="create_session", error=str(exc))
        raise
    finally:
        conn.close()

    emit(
        "session_created",
        session_id=session_id,
        scenario_id=scenario_id,
        start_id=start.id,
        ephemeral=ephemeral,
    )

    assets = session_assets(scenario)
    _emit_session_assets(session_id, assets)

    return SessionDetail(
        id=session_id,
        scenario_id=scenario_id,
        scenario_name=scenario.meta.name,
        prologue=start.prologue,
        play_guide=start.play_guide,
        turns=[],
        hud=hud,
        assets=assets,
    )


def list_sessions() -> list[SessionSummary]:
    conn = _connect()
    try:
        cur = conn.execute(
            """
            SELECT s.id, s.scenario_id, s.scenario_name, s.updated_at, s.created_at, s.hud,
                   (SELECT COUNT(*) FROM events e WHERE e.session_id = s.id AND e.kind = 'player_turn')
            FROM sessions s
            WHERE s.ephemeral = 0
            ORDER BY s.updated_at DESC, s.created_at DESC, s.id DESC
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    summaries = []
    for row in rows:
        hud = json.loads(row[5])
        summaries.append(
            SessionSummary(
                id=row[0],
                scenario_id=row[1],
                scenario_name=row[2],
                turn_count=row[6],
                updated_at=row[3],
                location=hud["location"],
            )
        )
    return summaries


def get_session_row(session_id: str) -> SessionRow:
    conn = _connect()
    try:
        cur = conn.execute(
            "SELECT id, scenario_id, start_id, hud FROM sessions WHERE id = ?",
            (session_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise SessionNotFound(session_id)

    return SessionRow(
        id=row[0],
        scenario_id=row[1],
        start_id=row[2],
        hud=HudState.model_validate_json(row[3]),
    )


def get_session(session_id: str) -> SessionDetail:
    row = get_session_row(session_id)
    try:
        scenario = load_scenario(row.scenario_id)
        start = scenario.starts[row.start_id]
    except (ScenarioError, KeyError):
        raise ScenarioNotFound(row.scenario_id) from None

    events = read_events(session_id, kinds=("player_turn", "narrator_turn"))
    turns = _build_turns(events)

    assets = session_assets(scenario)
    _emit_session_assets(session_id, assets)

    return SessionDetail(
        id=row.id,
        scenario_id=row.scenario_id,
        scenario_name=scenario.meta.name,
        prologue=start.prologue,
        play_guide=start.play_guide,
        turns=turns,
        hud=row.hud,
        assets=assets,
    )


def delete_session(session_id: str) -> None:
    conn = _connect()
    try:
        cur = conn.execute("SELECT ephemeral FROM sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
        if row is None:
            raise SessionNotFound(session_id)
        if row[0] == 0:
            raise SessionNotEphemeral(session_id)

        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
        events_deleted = cur.rowcount
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        emit("session_db_error", op="delete_session", error=str(exc))
        raise
    finally:
        conn.close()

    emit("session_deleted", session_id=session_id, events=events_deleted)


def purge_ephemeral_sessions() -> int:
    conn = _connect()
    try:
        cur = conn.execute("SELECT id FROM sessions WHERE ephemeral = 1")
        ids = [row[0] for row in cur.fetchall()]
        if not ids:
            return 0

        with conn:
            for session_id in ids:
                conn.execute("DELETE FROM events WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    finally:
        conn.close()

    count = len(ids)
    emit("ephemeral_sessions_purged", count=count)
    return count


def read_events(session_id: str, kinds: tuple[str, ...] | None = None) -> list[Event]:
    conn = _connect()
    try:
        if kinds:
            placeholders = ",".join("?" * len(kinds))
            cur = conn.execute(
                f"SELECT id, seq, kind, payload, created_at FROM events "
                f"WHERE session_id = ? AND kind IN ({placeholders}) ORDER BY seq",
                (session_id, *kinds),
            )
        else:
            cur = conn.execute(
                "SELECT id, seq, kind, payload, created_at FROM events WHERE session_id = ? ORDER BY seq",
                (session_id,),
            )
        rows = cur.fetchall()
    finally:
        conn.close()

    return [
        Event(id=row[0], seq=row[1], kind=row[2], payload=json.loads(row[3]), created_at=row[4])
        for row in rows
    ]


def _append_in_tx(conn: sqlite3.Connection, session_id: str, events: list[NewEvent], now: str) -> int:
    """Insert events with contiguous per-session seq. Must run inside an open transaction."""
    cur = conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events WHERE session_id = ?", (session_id,))
    seq = cur.fetchone()[0]
    for kind, payload in events:
        seq += 1
        conn.execute(
            "INSERT INTO events (session_id, seq, kind, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, seq, kind, json.dumps(payload, ensure_ascii=False), now),
        )
    return seq


def append_events(session_id: str, events: list[NewEvent], hud: HudState | None = None) -> None:
    now = _now_iso()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _append_in_tx(conn, session_id, events, now)
        if hud is not None:
            conn.execute(
                "UPDATE sessions SET updated_at = ?, hud = ? WHERE id = ?",
                (now, hud.model_dump_json(), session_id),
            )
        else:
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        emit("session_db_error", op="append_events", error=str(exc))
        raise
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_compact(session_id: str) -> tuple[str | None, int | None]:
    conn = _connect()
    try:
        cur = conn.execute("SELECT compact, compact_seq FROM sessions WHERE id = ?", (session_id,))
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        raise SessionNotFound(session_id)

    return row[0], row[1]


def set_compact(session_id: str, text: str, covered_seq: int, payload: dict) -> None:
    now = _now_iso()
    event_payload = {"text": text, **payload}
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _append_in_tx(conn, session_id, [("compact", event_payload)], now)
        conn.execute(
            "UPDATE sessions SET compact = ?, compact_seq = ?, updated_at = ? WHERE id = ?",
            (text, covered_seq, now, session_id),
        )
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        emit("session_db_error", op="set_compact", error=str(exc))
        raise
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _build_turns(events: list[Event]) -> list[TurnView]:
    turns: list[TurnView] = []
    index = 0
    for event in events:
        if event.kind == "player_turn":
            index += 1
        role: Literal["player", "narrator"] = "player" if event.kind == "player_turn" else "narrator"
        turns.append(TurnView(index=index, role=role, text=event.payload["text"]))
    return turns
