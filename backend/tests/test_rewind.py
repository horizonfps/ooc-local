import pytest
from fastapi.testclient import TestClient

from app import main, replay, sessions
from app.config import Config

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

START_WITH_ACHIEVEMENT = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
  time: "07:50"
achievements:
  - id: marco-um
    name: Primeiro marco
    type: achievement
    rarity: common
    condition: sempre
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


def _write_scenario(root, scenario_id="exemplo-escola", *, start=DEFAULT_START, stats=STATS_YAML):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(start, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    if stats is not None:
        (scenario_path / "stats.yaml").write_text(stats, encoding="utf-8")

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


def _config():
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
        }
    )


def _turn_events(text, narrator_text, *, mode="do", stats=None):
    player_payload = {"text": text}
    if mode is not None:
        player_payload["mode"] = mode
    events = [
        ("player_turn", player_payload),
        ("narrator_turn", {"text": narrator_text, "suggestions": []}),
    ]
    events.extend(stats or [])
    return events


def _stat_event(stat_id, delta, value, source="tag"):
    return ("stat", {"id": stat_id, "delta": delta, "value": value, "source": source})


def _achievement_event(id_, name, type_, rarity, turn, text="marco atingido"):
    return ("achievement", {"id": id_, "type": type_, "rarity": rarity, "name": name, "turn": turn, "text": text})


def _play_turns(session_id, count, *, stat_start=40):
    value = stat_start
    for i in range(1, count + 1):
        value += 1
        sessions.append_events(
            session_id,
            _turn_events(f"turno {i}", f"narra {i}", stats=[_stat_event("reputacao", 1, value)]),
        )


def test_rewind_two_of_five_turns(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    _play_turns(detail.id, 5)

    before = replay.replay_session(detail.id)
    result = sessions.rewind_session(detail.id, 2)

    assert {t.index for t in result.turns} == {1, 2}
    assert result.hud.turn == before.turns[1].hud_end.turn
    assert result.hud.stats["reputacao"] == before.turns[1].hud_end.stats["reputacao"]

    again = sessions.get_session(detail.id)
    assert {t.index for t in again.turns} == {1, 2}


def test_rewind_to_zero(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    _play_turns(detail.id, 3)

    result = sessions.rewind_session(detail.id, 0)

    assert result.turns == []
    assert result.hud.turn == 0
    assert result.hud.stats["reputacao"] == 40


def test_rewind_then_play_again_via_route(scenarios_root, monkeypatch):
    from app import turn as turn_module
    from app.llm.openai_compat import OpenAICompatProvider

    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn_module, "load_config", lambda: _config())

    async def fake_stream(self, messages, model):
        for chunk in ["novo turno"]:
            yield chunk

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()
    _play_turns(session["id"], 3)

    response = client.post(f"/api/sessions/{session['id']}/rewind", json={"turn": 1})
    assert response.status_code == 200
    assert {t["index"] for t in response.json()["turns"]} == {1}

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "eu continuo"}
    ) as stream_response:
        list(stream_response.iter_lines())

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert [t["text"] for t in detail["turns"] if t["role"] == "player"] == ["turno 1", "eu continuo"]


def test_rewind_reopens_ended_session_and_accepts_turn(scenarios_root, monkeypatch):
    from app import turn as turn_module
    from app.llm.openai_compat import OpenAICompatProvider

    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())
    monkeypatch.setattr(turn_module, "load_config", lambda: _config())

    async def fake_stream(self, messages, model):
        for chunk in ["novo turno"]:
            yield chunk

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    client = TestClient(main.app)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()
    _play_turns(session["id"], 2)
    sessions.append_events(session["id"], [("session_ended", {"turn": 2})])

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["ended"] is True

    response = client.post(f"/api/sessions/{session['id']}/rewind", json={"turn": 1})
    assert response.status_code == 200
    assert response.json()["ended"] is False

    turn_response = client.post(f"/api/sessions/{session['id']}/turn", json={"message": "eu sigo"})
    assert turn_response.status_code == 200


def test_two_rewinds_in_sequence_do_not_resurrect_first_range(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    _play_turns(detail.id, 5)

    sessions.rewind_session(detail.id, 4)
    _play_turns(detail.id, 1)
    result = sessions.rewind_session(detail.id, 2)

    assert {t.index for t in result.turns} == {1, 2}
    assert [t.text for t in result.turns if t.role == "player"] == ["turno 1", "turno 2"]


def test_rewind_does_not_delete_rows(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    _play_turns(detail.id, 3)

    conn = sessions._connect()
    try:
        before = conn.execute(
            "SELECT COUNT(*) FROM events WHERE session_id = ?", (detail.id,)
        ).fetchone()[0]
    finally:
        conn.close()

    sessions.rewind_session(detail.id, 1)

    conn = sessions._connect()
    try:
        after = conn.execute(
            "SELECT COUNT(*) FROM events WHERE session_id = ?", (detail.id,)
        ).fetchone()[0]
    finally:
        conn.close()

    assert after == before + 1


def test_discarded_achievement_leaves_session_but_stays_in_gallery(scenarios_root):
    _write_scenario(scenarios_root, start=START_WITH_ACHIEVEMENT)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events("turno um", "narra um")
        + [_achievement_event("marco-um", "Primeiro marco", "achievement", "common", 1)],
    )
    sessions.append_events(detail.id, _turn_events("turno dois", "narra dois"))

    result = sessions.rewind_session(detail.id, 0)
    assert result.achievements == []

    client = TestClient(main.app)
    gallery = client.get("/api/scenarios/exemplo-escola/gallery").json()
    entry = next(
        e for s in gallery["starts"] for e in s["achievements"] if e["id"] == "marco-um"
    )
    assert entry["unlocked"] is True


def test_discarded_compact_stops_being_used(scenarios_root):
    from app import turn as turn_module

    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(detail.id, _turn_events("turno um", "narra um"))
    seq_after_first = sessions.read_events(detail.id)[-1].seq
    sessions.set_compact(detail.id, "resumo antigo", seq_after_first, {"to_seq": seq_after_first})
    sessions.append_events(detail.id, _turn_events("turno dois", "narra dois"))
    sessions.set_compact(detail.id, "resumo novo", seq_after_first + 2, {"to_seq": seq_after_first + 2})

    sessions.rewind_session(detail.id, 1)

    text, compact_seq = sessions.get_compact(detail.id)
    assert text == "resumo antigo"
    assert compact_seq == seq_after_first

    # the window the narrator reads: with the discarded compact gone, there is
    # nothing left to summarize past the surviving turn.
    assert turn_module.history_events(detail.id, compact_seq) == []


def test_cut_seq_at_last_turn_with_trailing_events(scenarios_root):
    _write_scenario(scenarios_root, start=START_WITH_ACHIEVEMENT)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events("turno um", "narra um", stats=[_stat_event("reputacao", 1, 41)])
        + [
            ("cast", {"ids": ["chloe"], "source": "director"}),
            ("minds", {"entries": {}}),
            _achievement_event("marco-um", "Primeiro marco", "achievement", "common", 1),
        ],
    )

    rep = replay.replay_session(detail.id)
    all_events = sessions.read_events(detail.id)

    cut = replay.cut_seq(rep, 1)

    assert cut == all_events[-1].seq


def test_cut_seq_drops_a_meta_command_that_happened_after_the_target_turn(scenarios_root):
    """A `/status`-style command played after turn 1 is discarded by a rewind
    to turn 1: it happened after the target, so it has nothing to attach to."""
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(detail.id, _turn_events("turno um", "narra um"))
    sessions.append_events(
        detail.id,
        [
            ("meta_player_turn", {"text": "/status", "command": "status"}),
            ("meta_narrator_turn", {"text": "status: ok"}),
        ],
    )
    sessions.append_events(detail.id, _turn_events("turno dois", "narra dois"))

    result = sessions.rewind_session(detail.id, 1)

    assert [t.text for t in result.turns] == ["turno um", "narra um"]
    assert all(not t.meta for t in result.turns)


def test_cut_seq_rejects_out_of_range_turn(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(detail.id, _turn_events("turno um", "narra um"))

    rep = replay.replay_session(detail.id)

    with pytest.raises(replay.InvalidRewindTarget):
        replay.cut_seq(rep, 2)
    with pytest.raises(replay.InvalidRewindTarget):
        replay.cut_seq(rep, -1)


def test_rewind_target_cast_minds_and_suggestions_match_the_target_turn(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events("turno um", "narra um")
        + [
            ("cast", {"ids": ["chloe"], "source": "director"}),
            (
                "minds",
                {"entries": {"chloe": {"attitude": "curiosa", "emoji": "🤔", "event": "turno um"}}},
            ),
        ],
    )
    sessions.append_events(
        detail.id,
        _turn_events("turno dois", "narra dois", mode="say")
        + [
            ("cast", {"ids": [], "source": "director"}),
            ("minds", {"entries": {}}),
        ],
    )

    result = sessions.rewind_session(detail.id, 1)

    assert [member.id for member in result.cast] == ["chloe"]
    assert "chloe" in result.minds
    assert result.suggestions == []


def test_dynamic_stat_created_in_a_discarded_turn_leaves_the_hud(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(detail.id, _turn_events("turno um", "narra um"))
    sessions.append_events(
        detail.id,
        _turn_events(
            "turno dois",
            "narra dois",
            stats=[
                (
                    "stat",
                    {
                        "id": "confianca",
                        "delta": 1,
                        "value": 1,
                        "source": "tag",
                        "name": "Confianca",
                        "min": 0,
                        "max": 10,
                    },
                )
            ],
        ),
    )

    before = replay.replay_session(detail.id)
    assert "confianca" in before.turns[1].hud_end.dynamic_stats

    result = sessions.rewind_session(detail.id, 1)

    assert "confianca" not in result.hud.dynamic_stats


def test_session_rewound_and_rejected_events_are_emitted(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    _play_turns(detail.id, 3)

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(sessions, "emit", lambda name, **props: events.append((name, props)))

    sessions.rewind_session(detail.id, 2)

    rewound = [props for name, props in events if name == "session_rewound"]
    assert len(rewound) == 1
    assert rewound[0]["turn"] == 2
    assert rewound[0]["dropped_turns"] == 1

    events.clear()
    with pytest.raises(sessions.RewindTargetNotFound):
        sessions.rewind_session(detail.id, 99)

    rejected = [props for name, props in events if name == "rewind_rejected"]
    assert rejected == [{"session_id": detail.id, "turn": 99, "reason": "out_of_range"}]


def test_rewind_out_of_range_is_409(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    _play_turns(detail.id, 5)

    client = TestClient(main.app)
    response = client.post(f"/api/sessions/{detail.id}/rewind", json={"turn": 99})
    assert response.status_code == 409
    assert response.json() == {"detail": "turn out of range"}


def test_rewind_negative_turn_is_422(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    client = TestClient(main.app)
    response = client.post(f"/api/sessions/{detail.id}/rewind", json={"turn": -1})
    assert response.status_code == 422


def test_rewind_session_not_found_is_404(scenarios_root):
    client = TestClient(main.app)
    response = client.post("/api/sessions/nao-existe/rewind", json={"turn": 0})
    assert response.status_code == 404
    assert response.json() == {"detail": "session not found"}


def test_rewind_scenario_missing_from_disk_is_404(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    _play_turns(detail.id, 1)

    import shutil

    shutil.rmtree(scenarios_root / "exemplo-escola")

    client = TestClient(main.app)
    response = client.post(f"/api/sessions/{detail.id}/rewind", json={"turn": 0})
    assert response.status_code == 404
    assert response.json() == {"detail": "scenario not found"}


def test_rewind_disabled_by_flag_is_503_and_writes_nothing(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    _play_turns(detail.id, 2)

    monkeypatch.setattr(
        main,
        "load_config",
        lambda: Config.model_validate(
            {
                "providers": {"local": {"base_url": "http://x/v1"}},
                "models": {"narrator": {"provider": "local", "model": "m"}},
                "flags": {"rewind": False},
            }
        ),
    )

    before = sessions.read_events(detail.id)
    client = TestClient(main.app)
    response = client.post(f"/api/sessions/{detail.id}/rewind", json={"turn": 1})
    assert response.status_code == 503
    assert response.json() == {"detail": "rewind disabled by flag"}

    after = sessions.read_events(detail.id)
    assert before == after
