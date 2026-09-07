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
characters: [chloe]
achievements:
  - id: primeira-descoberta
    name: Primeira descoberta
    type: achievement
    rarity: rare
    condition: descobriu algo
    min_turn: 3
"""

MULTI_ACHIEVEMENTS_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
  time: "07:50"
characters: [chloe]
achievements:
  - id: marco-um
    name: Marco um
    type: achievement
    rarity: common
    condition: primeiro marco
    min_turn: 3
  - id: marco-dois
    name: Marco dois
    type: achievement
    rarity: common
    condition: segundo marco
    min_turn: 3
  - id: marco-tres
    name: Marco tres
    type: achievement
    rarity: common
    condition: terceiro marco
    min_turn: 3
"""

ENDING_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
  time: "07:50"
characters: [chloe]
achievements:
  - id: marco-e-final
    name: Marco e final
    type: achievement
    rarity: common
    condition: um marco
    min_turn: 3
  - id: final-feliz
    name: Final feliz
    type: ending
    rarity: epic
    condition: chegou ao fim
    min_turn: 3
"""

GATED_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
  time: "07:50"
characters: [chloe]
achievements:
  - id: gate-alto
    name: Gate alto
    type: achievement
    rarity: rare
    condition: reputacao alta
    min_turn: 3
    stat_gates:
      - id: reputacao
        at_least: 90
"""

STATS_YAML = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 40
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


def _write_scenario(root, scenario_id="exemplo-escola", *, start=DEFAULT_START, stats=STATS_YAML):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    scenario_path.joinpath("scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
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


def _config(flags=None, with_utility=True):
    models = {"narrator": {"provider": "local", "model": "narrator-model"}}
    if with_utility:
        models["utility"] = {"provider": "local", "model": "utility-model"}
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": models,
            "flags": {"director": False, "hud_judge": False, "minds": False, **(flags or {})},
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


def _setup(scenarios_root, monkeypatch, *, start=DEFAULT_START, flags=None, config=None):
    _write_scenario(scenarios_root, start=start)
    config = config or _config(flags)
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(turn, "load_config", lambda: config)
    return TestClient(main.app)


def _turn(client, session_id, message="continua"):
    with client.stream(
        "POST", f"/api/sessions/{session_id}/turn", json={"message": message}
    ) as response:
        return response.status_code, _stream_events(response)


def _route(narrator_replies, utility_replies=()):
    """Each model has its own queue, consumed call after call, in the order run_turn issues them."""
    narrator_queue = list(narrator_replies)
    utility_queue = list(utility_replies)

    async def fake_stream(self, messages, model):
        queue = utility_queue if model == "utility-model" else narrator_queue
        reply = queue.pop(0)
        for delta in reply if isinstance(reply, list) else [reply]:
            yield delta

    return fake_stream


def test_turns_below_threshold_do_not_check(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _route(["turno 1", "turno 2"]))
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    _turn(client, session["id"])
    _turn(client, session["id"])

    assert [name for name, _ in emitted if name.startswith("achievements_")] == []


def test_unlock_at_threshold_grants_and_continues(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["turno 1", "turno 2", "turno 3", "nota do marco"],
            ['{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'],
        ),
    )
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])

    assert status == 200
    hud_event = next(e for e in events if "hud" in e)
    assert hud_event["hud"]["turn"] == 3

    achievements_event = next(e for e in events if "achievements" in e)
    assert achievements_event["achievements"][0]["id"] == "primeira-descoberta"
    assert achievements_event["achievements"][0]["turn"] == hud_event["hud"]["turn"]
    assert not any("ended" in e for e in events)

    stored = [e for e in sessions.read_events(session["id"]) if e.kind == "achievement"]
    assert len(stored) == 1
    assert stored[0].payload["text"] == "nota do marco"
    assert stored[0].payload["turn"] == hud_event["hud"]["turn"]

    applied = [props for name, props in emitted if name == "achievements_applied"]
    assert applied[0]["ids"] == ["primeira-descoberta"]
    assert applied[0]["model"] == "utility-model"
    assert applied[0]["structured"] is False

    # session still accepts turns
    status2, _ = _turn(client, session["id"])
    assert status2 == 200


def test_two_achievements_in_separate_checks_do_not_end_session(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, start=MULTI_ACHIEVEMENTS_START)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["t1", "t2", "t3", "nota1", "t4", "t5", "t6", "nota2"],
            [
                '{"verdicts": [{"id": "marco-um", "met": true}, {"id": "marco-dois", "met": false}, '
                '{"id": "marco-tres", "met": false}]}',
                '{"verdicts": [{"id": "marco-dois", "met": true}, {"id": "marco-tres", "met": false}]}',
            ],
        ),
    )

    for _ in range(6):
        status, events = _turn(client, session["id"])
        assert status == 200

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["ended"] is False
    assert {a["id"] for a in detail["achievements"]} == {"marco-um", "marco-dois"}


def test_ending_grants_epilogue_and_locks_session(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, start=ENDING_START)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["t1", "t2", "t3", "nota do marco", "texto do epilogo"],
            ['{"verdicts": [{"id": "marco-e-final", "met": true}, {"id": "final-feliz", "met": true}]}'],
        ),
    )
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    append_calls = []
    original_append_events = turn.append_events
    monkeypatch.setattr(
        turn,
        "append_events",
        lambda *args, **kwargs: (append_calls.append((args, kwargs)), original_append_events(*args, **kwargs))[1],
    )

    _turn(client, session["id"])
    _turn(client, session["id"])
    append_calls.clear()
    status, events = _turn(client, session["id"])
    assert status == 200

    achievements_idx = next(i for i, e in enumerate(events) if "achievements" in e)
    ended_idx = next(i for i, e in enumerate(events) if "ended" in e)
    hud_idx = next(i for i, e in enumerate(events) if "hud" in e)
    assert achievements_idx < ended_idx < hud_idx

    achievements_payload = events[achievements_idx]["achievements"]
    assert [a["id"] for a in achievements_payload] == ["marco-e-final", "final-feliz"]
    assert achievements_payload[1]["type"] == "ending"
    assert events[ended_idx]["ended"]["achievementId"] == "final-feliz"

    # The achievement, ending and session_ended events must land in the same
    # append_events call as `hud`; splitting it reopens a replay inconsistency window.
    post_block_calls = [
        call for call in append_calls
        if any(kind in ("achievement", "session_ended") for kind, _ in call[0][1])
    ]
    assert len(post_block_calls) == 1
    call_args, call_kwargs = post_block_calls[0]
    recorded_kinds = [kind for kind, _ in call_args[1]]
    assert recorded_kinds.count("achievement") == 2
    assert "session_ended" in recorded_kinds
    assert call_kwargs.get("hud") is not None

    stored = sessions.read_events(session["id"])
    stored_kinds = [e.kind for e in stored]
    assert stored_kinds.count("achievement") == 2
    assert stored_kinds.index("session_ended") == len(stored_kinds) - 1

    achievement_events = [e for e in stored if e.kind == "achievement"]
    assert achievement_events[0].payload["id"] == "marco-e-final"
    assert achievement_events[1].payload["id"] == "final-feliz"
    assert achievement_events[0].seq < achievement_events[1].seq

    written = [props for name, props in emitted if name == "epilogue_written"]
    assert {props["kind"]: props["model"] for props in written} == {
        "milestone": "narrator-model",
        "ending": "narrator-model",
    }

    status2, _ = _turn(client, session["id"])
    assert status2 == 409


def test_epilogue_error_does_not_end_session(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, start=ENDING_START)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    narrator_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"verdicts": [{"id": "marco-e-final", "met": true}, {"id": "final-feliz", "met": true}]}'
            return
        narrator_calls.append(messages)
        if len(narrator_calls) == 5:  # the ending call
            raise RuntimeError("narrator offline")
        yield "turno normal" if len(narrator_calls) <= 3 else "nota do marco"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200
    assert not any("ended" in e for e in events)

    stored_kinds = [e.kind for e in sessions.read_events(session["id"])]
    assert "session_ended" not in stored_kinds

    written = [props for name, props in emitted if name == "epilogue_written" and props["kind"] == "ending"]
    assert written[0]["error"] is not None
    assert written[0]["model"] == "narrator-model"

    status2, _ = _turn(client, session["id"])
    assert status2 == 200


def test_epilogue_only_tag_is_treated_as_failure(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, start=ENDING_START)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["t1", "t2", "t3", "nota do marco", "[LOC:sala]"],
            ['{"verdicts": [{"id": "marco-e-final", "met": true}, {"id": "final-feliz", "met": true}]}'],
        ),
    )

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200
    assert not any("ended" in e for e in events)

    stored_kinds = [e.kind for e in sessions.read_events(session["id"])]
    assert "session_ended" not in stored_kinds


def test_epilogue_tag_is_stripped_and_does_not_move_location(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, start=ENDING_START)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["t1", "t2", "t3", "nota do marco", "final feliz [LOC:sala] de verdade"],
            ['{"verdicts": [{"id": "marco-e-final", "met": true}, {"id": "final-feliz", "met": true}]}'],
        ),
    )

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200

    hud_event = next(e for e in events if "hud" in e)
    assert hud_event["hud"]["location"] == "patio"

    stored = [e for e in sessions.read_events(session["id"]) if e.kind == "achievement" and e.payload["type"] == "ending"]
    assert "[LOC:sala]" not in stored[0].payload["text"]
    assert "final feliz" in stored[0].payload["text"]


def test_milestone_failure_records_event_without_text(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    narrator_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'
            return
        narrator_calls.append(messages)
        if len(narrator_calls) == 4:  # the milestone call
            raise RuntimeError("narrator offline")
        yield "turno normal"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200

    stored = [e for e in sessions.read_events(session["id"]) if e.kind == "achievement"]
    assert len(stored) == 1
    assert "text" not in stored[0].payload

    written = [props for name, props in emitted if name == "epilogue_written" and props["kind"] == "milestone"]
    assert written[0]["error"] is not None
    assert written[0]["model"] == "narrator-model"


def test_milestone_empty_after_cleanup_is_treated_as_failure(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["t1", "t2", "t3", "[LOC:sala]"],
            ['{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'],
        ),
    )
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200

    stored = [e for e in sessions.read_events(session["id"]) if e.kind == "achievement"]
    assert len(stored) == 1
    assert "text" not in stored[0].payload

    hud_event = next(e for e in events if "hud" in e)
    assert hud_event["hud"]["location"] == "patio"

    written = [props for name, props in emitted if name == "epilogue_written" and props["kind"] == "milestone"]
    assert written[0]["error"] is not None
    assert written[0]["chars"] == 0


def test_three_achievements_cap_milestone_calls(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, start=MULTI_ACHIEVEMENTS_START)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    narrator_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield (
                '{"verdicts": [{"id": "marco-um", "met": true}, {"id": "marco-dois", "met": true}, '
                '{"id": "marco-tres", "met": true}]}'
            )
            return
        narrator_calls.append(messages)
        if len(narrator_calls) <= 3:
            yield f"turno {len(narrator_calls)}"
        else:
            yield "nota do marco"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, _ = _turn(client, session["id"])
    assert status == 200

    milestone_calls = len(narrator_calls) - 3
    assert milestone_calls == 2

    stored = [e for e in sessions.read_events(session["id"]) if e.kind == "achievement"]
    assert len(stored) == 3
    with_text = [e for e in stored if e.payload.get("text")]
    assert len(with_text) == 2


def test_gated_candidate_barred_by_stat(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, start=GATED_START)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield '{"verdicts": []}'
        else:
            yield "turno normal"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    _turn(client, session["id"])
    _turn(client, session["id"])
    _turn(client, session["id"])

    assert utility_calls == []
    checked = [props for name, props in emitted if name == "achievements_checked"]
    assert checked[0]["called"] is False
    assert checked[0]["candidates"] == 0


def test_already_unlocked_is_not_candidate_again(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()
    session_id = session["id"]

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["t1", "t2", "t3", "nota"],
            ['{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'],
        ),
    )
    _turn(client, session_id)
    _turn(client, session_id)
    _turn(client, session_id)

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield '{"verdicts": []}'
        else:
            yield "turno normal"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    for _ in range(3):
        _turn(client, session_id)

    checked = [props for name, props in emitted if name == "achievements_checked"]
    assert checked[-1]["candidates"] == 0
    stored = [e for e in sessions.read_events(session_id) if e.kind == "achievement"]
    assert len(stored) == 1


def test_flag_off_disables_achievements(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, flags={"achievements": False})
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield '{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'
        else:
            yield "turno normal"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    for _ in range(3):
        _turn(client, session["id"])

    assert utility_calls == []
    assert [name for name, _ in emitted if name.startswith("achievements_")] == []
    stored = [e for e in sessions.read_events(session["id"]) if e.kind == "achievement"]
    assert stored == []


def test_command_turn_never_checks_even_at_threshold(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()
    session_id = session["id"]

    utility_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            utility_calls.append(messages)
            yield '{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'
        else:
            yield "turno normal"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    # Three normal turns bring hud.turn to the check threshold. min_turn (3) makes
    # the achievement eligible, so the third normal turn unlocks it legitimately.
    _turn(client, session_id)
    _turn(client, session_id)
    _turn(client, session_id)
    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["hud"]["turn"] == 3
    utility_calls.clear()
    stored_before = [e for e in sessions.read_events(session_id) if e.kind == "achievement"]

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    status, events = _turn(client, session_id, message="/diary")
    assert status == 200

    # Command turns don't call `advance`, so hud.turn stays at the threshold,
    # yet the command path returns before the achievement block: no check happens.
    detail_after = client.get(f"/api/sessions/{session_id}").json()
    assert detail_after["hud"]["turn"] == 3
    assert utility_calls == []
    assert [name for name, _ in emitted if name.startswith("achievements_")] == []
    stored_after = [e for e in sessions.read_events(session_id) if e.kind == "achievement"]
    assert stored_after == stored_before


def test_prose_from_utility_rejects_and_writes_nothing(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    long_prose = "isso nao e json " * 20

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(["t1", "t2", "t3"], [long_prose]),
    )
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200

    rejected = [props for name, props in emitted if name == "achievements_rejected"]
    assert len(rejected) == 1
    from app.achievements import ACHIEVEMENT_RAW_LOG_CHARS

    assert rejected[0]["raw"] == long_prose[:ACHIEVEMENT_RAW_LOG_CHARS]
    assert rejected[0]["model"] == "utility-model"
    assert rejected[0]["structured"] is False

    stored = [e for e in sessions.read_events(session["id"]) if e.kind == "achievement"]
    assert stored == []


def test_stream_publishes_milestone_text(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["turno 1", "turno 2", "turno 3", "nota do marco"],
            ['{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'],
        ),
    )

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200

    achievements_event = next(e for e in events if "achievements" in e)
    assert achievements_event["achievements"][0]["text"] == "nota do marco"


def test_stream_publishes_epilogue_text(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, start=ENDING_START)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["t1", "t2", "t3", "nota do marco", "texto do epilogo"],
            ['{"verdicts": [{"id": "marco-e-final", "met": true}, {"id": "final-feliz", "met": true}]}'],
        ),
    )

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200

    achievements_event = next(e for e in events if "achievements" in e)
    by_id = {a["id"]: a for a in achievements_event["achievements"]}
    assert by_id["marco-e-final"]["text"] == "nota do marco"
    assert by_id["final-feliz"]["text"] == "texto do epilogo"


def test_stream_achievement_without_text_omits_text(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    narrator_calls = []

    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield '{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'
            return
        narrator_calls.append(messages)
        if len(narrator_calls) == 4:  # the milestone call
            raise RuntimeError("narrator offline")
        yield "turno normal"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)

    _turn(client, session["id"])
    _turn(client, session["id"])
    status, events = _turn(client, session["id"])
    assert status == 200

    achievements_event = next(e for e in events if "achievements" in e)
    assert achievements_event["achievements"][0].get("text") is None


def test_read_achievements_and_session_detail_do_not_carry_text(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider,
        "stream_chat",
        _route(
            ["turno 1", "turno 2", "turno 3", "nota do marco"],
            ['{"verdicts": [{"id": "primeira-descoberta", "met": true}]}'],
        ),
    )

    _turn(client, session["id"])
    _turn(client, session["id"])
    _turn(client, session["id"])

    read = sessions.read_achievements(session["id"])
    assert all(not hasattr(a, "text") for a in read)

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert all("text" not in a for a in detail["achievements"])


def test_utility_unavailable_emits_failed_and_turn_completes(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, config=_config(with_utility=False))
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    async def fake_stream(self, messages, model):
        yield "turno normal"

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))

    status, events = _turn(client, session["id"])
    for _ in range(2):
        status, events = _turn(client, session["id"])

    assert status == 200
    assert any("hud" in e for e in events)
    failed = [props for name, props in emitted if name == "achievements_failed"]
    assert len(failed) == 1
    assert failed[0]["model"] is None
