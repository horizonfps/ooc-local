import json

import pytest

from app import dataset, sessions
from app.director import DIRECTOR_WINDOW_TURNS, build_director_messages
from app.judge import build_judge_messages
from app.minds import build_minds_messages
from app.replay import replay_session
from app.turn import events_to_messages

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

SCENARIO_EN_YAML = """\
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


def _write_scenario(root, scenario_id="exemplo-escola", *, scenario_yaml=SCENARIO_YAML, start=DEFAULT_START):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(start, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")
    (characters_dir / "mia.yaml").write_text(MIA_YAML, encoding="utf-8")

    (scenario_path / "stats.yaml").write_text(STATS_YAML, encoding="utf-8")

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
    """Same event shapes turn.py:460-469 appends for one turn (mirrors test_replay.py)."""
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


def _stat_tag(stat_id, delta, valid=True):
    return {"kind": "STAT", "args": [stat_id, str(delta)], "raw": f"[STAT:{stat_id}:{delta}]", "valid": valid}


def _stat_event(stat_id, delta, value, source):
    return ("stat", {"id": stat_id, "delta": delta, "value": value, "source": source})


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_export_happy_path_writes_matching_messages_and_labels(scenarios_root, tmp_path):
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
            cast=["chloe"],
            minds={"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}},
        ),
    )
    sessions.append_events(detail.id, _turn_events("eu falo", "voce fala"))

    out_dir = tmp_path / "out"
    counters = dataset.export_dataset(out_dir)

    assert counters["sessions"] == 1
    assert counters["turns"] == 2
    assert counters["judge"] == 2
    assert counters["director"] == 2
    assert counters["minds"] == 2
    assert counters["skipped_scenario"] == 0
    assert counters["skipped_inexact"] == 0

    judge_lines = _read_jsonl(out_dir / "judge.jsonl")
    director_lines = _read_jsonl(out_dir / "director.jsonl")
    minds_lines = _read_jsonl(out_dir / "minds.jsonl")

    assert len(judge_lines) == 2
    assert len(director_lines) == 2
    assert len(minds_lines) == 2

    replay = replay_session(detail.id)
    first = replay.turns[0]

    expected_judge_messages = build_judge_messages(
        replay.scenario, first.hud_after_tags, first.message, first.narrator_text, first.touched_ids
    )
    assert judge_lines[0]["messages"] == [m.model_dump() for m in expected_judge_messages]
    assert judge_lines[0]["engine_label"] == {"stats": {"reputacao": -5}}
    assert judge_lines[0]["applied"] is True

    window = events_to_messages(first.history_before[-(DIRECTOR_WINDOW_TURNS * 2) :], replay.locale)
    expected_director_messages = build_director_messages(
        replay.scenario, first.hud_start, first.cast_before, first.message, window
    )
    assert director_lines[0]["messages"] == [m.model_dump() for m in expected_director_messages]
    assert director_lines[0]["engine_label"] == {"scene": ["chloe"]}
    assert director_lines[0]["applied"] is True

    expected_minds_messages = build_minds_messages(
        replay.scenario, first.cast_after, first.minds_before, first.message, first.narrator_text
    )
    assert minds_lines[0]["messages"] == [m.model_dump() for m in expected_minds_messages]
    assert minds_lines[0]["engine_label"] == {
        "chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}
    }
    assert minds_lines[0]["applied"] is True

    for lines in (judge_lines, director_lines, minds_lines):
        for line in lines:
            assert line["scenario_id"] == "exemplo-escola"
            assert line["session_id"] == detail.id
            assert line["locale"] == "pt-br"
            assert line["split"] in ("train", "holdout")


def test_turn_without_effect_is_exported_with_applied_false(scenarios_root, tmp_path):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(detail.id, _turn_events("eu ando", "voce anda"))

    out_dir = tmp_path / "out"
    dataset.export_dataset(out_dir)

    judge_lines = _read_jsonl(out_dir / "judge.jsonl")
    director_lines = _read_jsonl(out_dir / "director.jsonl")
    minds_lines = _read_jsonl(out_dir / "minds.jsonl")

    assert judge_lines[0]["engine_label"] == {"stats": {}}
    assert judge_lines[0]["applied"] is False
    assert director_lines[0]["engine_label"] == {"scene": ["chloe", "mia"]}
    assert director_lines[0]["applied"] is False
    assert minds_lines[0]["engine_label"] == {}
    assert minds_lines[0]["applied"] is False


def test_locale_en_produces_english_prompt(scenarios_root, tmp_path):
    _write_scenario(scenarios_root, scenario_yaml=SCENARIO_EN_YAML)
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(detail.id, _turn_events("i walk", "you walk"))

    out_dir = tmp_path / "out"
    dataset.export_dataset(out_dir)

    judge_lines = _read_jsonl(out_dir / "judge.jsonl")
    assert judge_lines[0]["locale"] == "en"
    assert "PLAYER ACTION" in judge_lines[0]["messages"][1]["content"]


def test_two_scenarios_keep_correct_scenario_id(scenarios_root, tmp_path):
    _write_scenario(scenarios_root, scenario_id="escola-um")
    _write_scenario(scenarios_root, scenario_id="escola-dois")

    first = sessions.create_session("escola-um")
    sessions.append_events(first.id, _turn_events("eu ando", "voce anda"))
    second = sessions.create_session("escola-dois")
    sessions.append_events(second.id, _turn_events("eu corro", "voce corre"))

    out_dir = tmp_path / "out"
    dataset.export_dataset(out_dir)

    judge_lines = _read_jsonl(out_dir / "judge.jsonl")
    by_session = {line["session_id"]: line["scenario_id"] for line in judge_lines}
    assert by_session[first.id] == "escola-um"
    assert by_session[second.id] == "escola-dois"


def test_ephemeral_session_is_not_exported(scenarios_root, tmp_path):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola", ephemeral=True)
    sessions.append_events(detail.id, _turn_events("eu ando", "voce anda"))

    out_dir = tmp_path / "out"
    counters = dataset.export_dataset(out_dir)

    assert counters["sessions"] == 0
    assert counters["turns"] == 0
    judge_lines = _read_jsonl(out_dir / "judge.jsonl")
    assert judge_lines == []


def test_empty_database_creates_empty_files(scenarios_root, tmp_path, capsys):
    out_dir = tmp_path / "out"
    exit_code = dataset.main(["export", "--out", str(out_dir)])

    assert exit_code == 0
    assert (out_dir / "judge.jsonl").read_text(encoding="utf-8") == ""
    assert (out_dir / "director.jsonl").read_text(encoding="utf-8") == ""
    assert (out_dir / "minds.jsonl").read_text(encoding="utf-8") == ""

    out = capsys.readouterr().out
    assert "sessions=0 turns=0" in out


def test_rerun_overwrites_instead_of_appending(scenarios_root, tmp_path):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(detail.id, _turn_events("eu ando", "voce anda"))

    out_dir = tmp_path / "out"
    (out_dir).mkdir()
    (out_dir / "judge.jsonl").write_text("stale line that should be gone\n", encoding="utf-8")

    dataset.export_dataset(out_dir)

    content = (out_dir / "judge.jsonl").read_text(encoding="utf-8")
    assert "stale line" not in content
    assert len(content.splitlines()) == 1


def test_two_runs_are_byte_for_byte_identical(scenarios_root, tmp_path):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(
        detail.id,
        _turn_events("eu ando", "voce anda", cast=["chloe"], minds={"chloe": {"attitude": "curiosa", "emoji": "🙂", "event": "te viu"}}),
    )
    sessions.append_events(detail.id, _turn_events("eu falo", "voce fala"))

    out_dir = tmp_path / "out"
    dataset.export_dataset(out_dir)
    first_run = {name: (out_dir / name).read_bytes() for name in ("judge.jsonl", "director.jsonl", "minds.jsonl")}

    dataset.export_dataset(out_dir)
    second_run = {name: (out_dir / name).read_bytes() for name in ("judge.jsonl", "director.jsonl", "minds.jsonl")}

    assert first_run == second_run


def test_split_for_is_deterministic_and_matches_known_id():
    assert dataset.split_for("session-a") == dataset.split_for("session-a")

    ids = [f"session-{i}" for i in range(40)]
    holdout = [session_id for session_id in ids if dataset.split_for(session_id) == "holdout"]
    assert 0 <= len(holdout) <= 10


def test_deleted_scenario_is_skipped_and_counted(scenarios_root, tmp_path):
    _write_scenario(scenarios_root, scenario_id="vai-sumir")
    detail = sessions.create_session("vai-sumir")
    sessions.append_events(detail.id, _turn_events("eu ando", "voce anda"))

    import shutil

    shutil.rmtree(scenarios_root / "vai-sumir")

    out_dir = tmp_path / "out"
    counters = dataset.export_dataset(out_dir)

    assert counters["skipped_scenario"] == 1
    assert counters["sessions"] == 0
    assert (out_dir / "judge.jsonl").read_text(encoding="utf-8") == ""


def test_inexact_turn_is_not_exported(scenarios_root, tmp_path):
    """Mirrors test_replay.py's own trigger for exact=False: a narrator_turn event
    outside any open group (here, right after a meta turn closes the group to None)."""
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        [
            ("meta_player_turn", {"text": "/status", "command": "status"}),
            ("meta_narrator_turn", {"text": "..."}),
        ],
    )
    sessions.append_events(detail.id, [("narrator_turn", {"text": "linha orfa sem player_turn"})])
    sessions.append_events(detail.id, _turn_events("eu falo", "voce fala"))

    out_dir = tmp_path / "out"
    counters = dataset.export_dataset(out_dir)

    assert counters["skipped_inexact"] == 1
    for lines in (
        _read_jsonl(out_dir / "judge.jsonl"),
        _read_jsonl(out_dir / "director.jsonl"),
        _read_jsonl(out_dir / "minds.jsonl"),
    ):
        assert lines == []


def test_main_without_subcommand_raises_system_exit():
    with pytest.raises(SystemExit):
        dataset.main([])


def test_main_export_without_out_raises_system_exit():
    with pytest.raises(SystemExit):
        dataset.main(["export"])
