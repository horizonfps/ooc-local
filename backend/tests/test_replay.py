import pytest

from app import replay, sessions

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

TWO_CHAR_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
characters:
  - chloe
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

MIA_YAML = """\
name: Mia
role: aluna
appearance: alta
personality: quieta
voice: baixa
mind:
  feeling: cautelosa
  goal: proteger o irmao
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
    (characters_dir / "mia.yaml").write_text(MIA_YAML, encoding="utf-8")

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


def _turn_events(text, narrator_text, *, mode="do", tags=None, stats=None, cast=None, minds=None):
    """Builds the same event shapes turn.py:460-469 appends for one turn."""
    player_payload = {"text": text}
    if mode is not None:
        player_payload["mode"] = mode
    events = [
        ("player_turn", player_payload),
        ("narrator_turn", {"text": narrator_text, "suggestions": []}),
    ]
    for tag in tags or []:
        events.append(("tag", tag))
    events.extend(stats or [])
    if cast is not None:
        events.append(("cast", {"ids": cast, "source": "director"}))
    if minds is not None:
        events.append(("minds", {"entries": minds}))
    return events


def _loc_tag(text, valid=True):
    return {"kind": "LOC", "args": [text], "raw": f"[LOC:{text}]", "valid": valid}


def _stat_tag(stat_id, delta, valid=True):
    return {"kind": "STAT", "args": [stat_id, str(delta)], "raw": f"[STAT:{stat_id}:{delta}]", "valid": valid}


def _stat_event(stat_id, delta, value, source):
    return ("stat", {"id": stat_id, "delta": delta, "value": value, "source": source})


def test_full_turns_happy_path(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events(
            "eu ando",
            "voce anda",
            tags=[_loc_tag("sala"), _stat_tag("reputacao", 3)],
            stats=[_stat_event("reputacao", 3, 43, "tag")],
            cast=["chloe"],
            minds={"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}},
        ),
    )
    sessions.append_events(
        detail.id,
        _turn_events("eu falo", "voce fala", tags=[], stats=[]),
    )
    sessions.append_events(
        detail.id,
        _turn_events("eu saio", "voce sai", tags=[], stats=[]),
    )

    result = replay.replay_session(detail.id)

    assert [snapshot.turn for snapshot in result.turns] == [1, 2, 3]
    assert result.session_id == detail.id
    assert result.locale == "pt-br"

    first = result.turns[0]
    assert first.message == "eu ando"
    assert first.mode == "do"
    assert first.narrator_text == "voce anda"
    assert first.hud_start == detail.hud
    assert first.hud_after_tags.location == "sala"
    assert first.hud_after_tags.turn == 1
    assert first.hud_after_tags.stats["reputacao"] == 43
    assert first.touched_ids == ["reputacao"]
    assert first.cast_before == ["chloe", "mia"]
    assert first.cast_after == ["chloe"]
    assert first.minds_before == {}
    assert first.exact is True

    second = result.turns[1]
    assert second.hud_start == first.hud_end
    assert second.cast_before == ["chloe"]
    assert second.minds_before["chloe"].attitude == "curiosa"


def test_two_huds_per_turn_judge_vs_tag(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events(
            "eu ando",
            "voce anda",
            tags=[_stat_tag("reputacao", 3)],
            stats=[
                _stat_event("reputacao", 3, 43, "tag"),
                _stat_event("reputacao", -5, 38, "judge"),
            ],
        ),
    )

    result = replay.replay_session(detail.id)
    snapshot = result.turns[0]

    assert snapshot.hud_after_tags.stats["reputacao"] == 43
    assert snapshot.hud_end.stats["reputacao"] == 38


def test_stat_tag_clamped_without_stat_event_still_touched(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events("eu ando", "voce anda", tags=[_stat_tag("reputacao", 999)], stats=[]),
    )

    result = replay.replay_session(detail.id)
    snapshot = result.turns[0]

    assert snapshot.touched_ids == ["reputacao"]
    assert snapshot.hud_after_tags.stats["reputacao"] == 40
    assert snapshot.hud_end.stats["reputacao"] == 40


def test_cast_before_and_after(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id, _turn_events("eu ando", "voce anda", cast=["chloe", "mia"])
    )
    sessions.append_events(detail.id, _turn_events("eu falo", "voce fala"))

    result = replay.replay_session(detail.id)

    assert result.turns[0].cast_after == ["chloe", "mia"]
    assert result.turns[1].cast_before == ["chloe", "mia"]
    assert result.turns[1].cast_after == ["chloe", "mia"]


def test_explicit_start_characters_seed_cast_before_first_turn(scenarios_root):
    _write_scenario(scenarios_root, start=TWO_CHAR_START)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(detail.id, _turn_events("eu ando", "voce anda"))

    result = replay.replay_session(detail.id)

    assert result.turns[0].cast_before == ["chloe"]


def test_minds_before_propagates_to_next_turn(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events(
            "eu ando",
            "voce anda",
            minds={"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}},
        ),
    )
    sessions.append_events(detail.id, _turn_events("eu falo", "voce fala"))

    result = replay.replay_session(detail.id)

    assert result.turns[0].minds_before == {}
    assert result.turns[1].minds_before["chloe"].attitude == "curiosa"


def test_history_before_only_has_player_and_narrator_events(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events(
            "turno um", "narra um", tags=[_stat_tag("reputacao", 1)], stats=[_stat_event("reputacao", 1, 41, "tag")]
        ),
    )
    sessions.append_events(detail.id, _turn_events("turno dois", "narra dois", cast=["chloe"]))
    sessions.append_events(detail.id, _turn_events("turno tres", "narra tres"))

    result = replay.replay_session(detail.id)
    history = result.turns[2].history_before

    assert [event.kind for event in history] == [
        "player_turn",
        "narrator_turn",
        "player_turn",
        "narrator_turn",
    ]
    assert [event.payload["text"] for event in history] == [
        "turno um",
        "narra um",
        "turno dois",
        "narra dois",
    ]


def test_compact_applies_from_the_turn_it_was_recorded_on(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(detail.id, _turn_events("turno um", "narra um"))
    sessions.set_compact(detail.id, "resumo ate aqui", 2, {"replaced_turns": 1, "from_seq": 1, "to_seq": 2})
    sessions.append_events(detail.id, _turn_events("turno dois", "narra dois"))
    sessions.append_events(detail.id, _turn_events("turno tres", "narra tres"))

    result = replay.replay_session(detail.id)

    assert result.turns[0].compact is None
    assert result.turns[0].compact_seq is None
    assert result.turns[1].compact == "resumo ate aqui"
    assert result.turns[1].compact_seq == 2
    assert result.turns[2].compact == "resumo ate aqui"
    assert result.turns[2].compact_seq == 2


def test_meta_turn_is_skipped_and_not_in_history(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(detail.id, _turn_events("turno um", "narra um"))
    sessions.append_events(
        detail.id,
        [("meta_player_turn", {"text": "/status", "command": "status"}), ("meta_narrator_turn", {"text": "..."})],
    )
    sessions.append_events(detail.id, _turn_events("turno dois", "narra dois"))

    result = replay.replay_session(detail.id)

    assert len(result.turns) == 2
    assert result.turns[1].turn == 2
    assert [event.kind for event in result.turns[1].history_before] == ["player_turn", "narrator_turn"]


def test_session_without_turns_returns_empty_list(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    result = replay.replay_session(detail.id)

    assert result.turns == []


def test_scenario_deleted_raises_scenario_not_found(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    import shutil

    shutil.rmtree(scenarios_root / "exemplo-escola")

    with pytest.raises(replay.ScenarioNotFound):
        replay.replay_session(detail.id)


def test_session_not_found_raises():
    with pytest.raises(sessions.SessionNotFound):
        replay.replay_session("does-not-exist")


def test_dynamic_stat_created_by_judge_marks_exact_false_from_then_on(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        _turn_events(
            "eu ando", "voce anda", stats=[_stat_event("confianca", 0, 10, "judge")]
        ),
    )
    sessions.append_events(detail.id, _turn_events("eu falo", "voce fala"))

    result = replay.replay_session(detail.id)

    assert result.turns[0].exact is False
    assert result.turns[0].hud_end.dynamic_stats["confianca"].value == 10
    assert result.turns[1].exact is False


def test_player_turn_without_mode_is_none(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        [("player_turn", {"text": "eu ando"}), ("narrator_turn", {"text": "voce anda"})],
    )

    result = replay.replay_session(detail.id)

    assert result.turns[0].mode is None
    assert result.turns[0].suggestions == []


@pytest.mark.parametrize("mode", ["orphan_narrator", "missing_text"])
def test_corrupted_events_mark_exact_false_and_skip_snapshot(scenarios_root, mode):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    if mode == "orphan_narrator":
        sessions.append_events(detail.id, [("narrator_turn", {"text": "sem pergunta"})])
    else:
        sessions.append_events(detail.id, [("player_turn", {"text": "eu ando"}), ("narrator_turn", {})])

    sessions.append_events(detail.id, _turn_events("eu falo", "voce fala"))

    result = replay.replay_session(detail.id)

    assert len(result.turns) == 1
    assert result.turns[0].message == "eu falo"
    assert result.turns[0].exact is False
