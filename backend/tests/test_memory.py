import json

import pytest
from fastapi.testclient import TestClient

from app import main, sessions, turn
from app.config import Config
from app.llm.openai_compat import OpenAICompatProvider
from app.memory import (
    MemoryEntry,
    MemoryRejection,
    merge_memories,
    render_memories,
)

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


def _write_scenario(root, scenario_id="exemplo-escola"):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    scenario_path.joinpath("scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    return scenario_path


def _config(flags=None, with_utility=True):
    models = {"narrator": {"provider": "local", "model": "narrator-model"}}
    if with_utility:
        models["utility"] = {"provider": "local", "model": "utility-model"}
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": models,
            "flags": {
                "director": False,
                "hud_judge": False,
                "minds": False,
                "achievements": False,
                **(flags or {}),
            },
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


def _setup(scenarios_root, monkeypatch, *, flags=None, config=None):
    _write_scenario(scenarios_root)
    config = config or _config(flags)
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(turn, "load_config", lambda: config)
    return TestClient(main.app)


def _route_by_model(narrator_deltas, utility_reply):
    async def fake_stream(self, messages, model):
        if model == "utility-model":
            yield utility_reply
        else:
            for delta in narrator_deltas:
                yield delta

    return fake_stream


def _turn(client, session_id, message="continua"):
    with client.stream(
        "POST", f"/api/sessions/{session_id}/turn", json={"message": message}
    ) as response:
        return _stream_events(response)


def _run_turns(client, session, monkeypatch, n, utility_reply='{"entries": []}'):
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _route_by_model(["a narradora fala."], utility_reply)
    )
    events = None
    for _ in range(n):
        events = _turn(client, session["id"])
    return events


# --- unit tests -----------------------------------------------------------


def test_merge_memories_accepts_one_per_category():
    proposed = [
        {"id": "caderno", "category": "long_term", "text": "prometi devolver o caderno"},
        {"id": "amizade-chloe", "category": "relationship", "text": "Chloe confia no jogador"},
        {"id": "achar-sala", "category": "goal", "text": "encontrar a sala secreta"},
        {"id": "chovendo", "category": "temporary", "text": "está chovendo lá fora"},
    ]
    entries, rejections, evicted = merge_memories([], proposed, turn=3)
    assert {e.id for e in entries} == {"caderno", "amizade-chloe", "achar-sala", "chovendo"}
    assert rejections == []
    assert evicted == []


def test_merge_memories_rejects_invalid_category():
    entries, rejections, _ = merge_memories(
        [], [{"id": "x", "category": "user_note", "text": "nota"}], turn=1
    )
    assert entries == []
    assert rejections == [MemoryRejection(id="x", reason="invalid_category")]


def test_merge_memories_rejects_invalid_id():
    entries, rejections, _ = merge_memories(
        [], [{"id": "Bad Id!", "category": "goal", "text": "algo"}], turn=1
    )
    assert entries == []
    assert rejections[0].reason == "invalid_id"


def test_merge_memories_rejects_empty_text():
    entries, rejections, _ = merge_memories(
        [], [{"id": "vazio", "category": "goal", "text": "   "}], turn=1
    )
    assert entries == []
    assert rejections[0].reason == "empty"


def test_merge_memories_truncates_long_text():
    long_text = "x" * 500
    entries, _, _ = merge_memories(
        [], [{"id": "longo", "category": "goal", "text": long_text}], turn=1
    )
    assert len(entries[0].text) == 200


def test_merge_memories_ignores_duplicate_proposal():
    previous = [MemoryEntry(id="x", category="goal", text="algo", turn=1)]
    entries, rejections, _ = merge_memories(
        previous, [{"id": "x", "category": "goal", "text": "algo"}], turn=2
    )
    assert entries == previous
    assert rejections[0].reason == "duplicate"


def test_merge_memories_evicts_fifo_only_from_full_category():
    previous = [
        MemoryEntry(id=f"g{i}", category="goal", text=f"objetivo {i}", turn=i) for i in range(1, 7)
    ]
    proposed = [{"id": "g7", "category": "goal", "text": "objetivo 7"}]
    entries, _, evicted = merge_memories(previous, proposed, turn=7)
    assert [e.id for e in evicted] == ["g1"]
    assert {e.id for e in entries} == {f"g{i}" for i in range(2, 8)}


def test_merge_memories_preserves_player_source_when_not_mentioned():
    previous = [MemoryEntry(id="nota", category="user_note", text="minha nota", turn=1, source="player")]
    entries, _, _ = merge_memories(previous, [], turn=2)
    assert entries == previous


def test_merge_memories_preserves_player_source_against_replacement():
    previous = [MemoryEntry(id="nota", category="goal", text="minha nota", turn=1, source="player")]
    proposed = [{"id": "nota", "category": "goal", "text": "outra coisa"}]
    entries, rejections, _ = merge_memories(previous, proposed, turn=2)
    assert entries == previous
    assert rejections[0].reason == "player_owned"


def test_render_memories_empty_is_none():
    assert render_memories([], "pt-br") is None


def test_render_memories_orders_categories_and_user_note_last():
    entries = [
        MemoryEntry(id="a", category="temporary", text="chove", turn=1),
        MemoryEntry(id="b", category="user_note", text="nota do jogador", turn=1, source="player"),
        MemoryEntry(id="c", category="long_term", text="fato permanente", turn=1),
        MemoryEntry(id="d", category="relationship", text="relacao", turn=1),
        MemoryEntry(id="e", category="goal", text="objetivo", turn=1),
    ]
    body = render_memories(entries, "pt-br")
    for earlier, later in (
        ("fato permanente", "relacao"),
        ("relacao", "objetivo"),
        ("objetivo", "chove"),
        ("chove", "nota do jogador"),
    ):
        assert body.index(earlier) < body.index(later)


# --- integration through the route -----------------------------------------


def test_turn_not_multiple_of_k_does_not_call_utility(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    _run_turns(client, session, monkeypatch, 2)

    assert not any(name == "memories_checked" for name, _ in emitted)


def test_turn_three_with_valid_proposal_records_one_event(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_reply = json.dumps(
        {"entries": [{"id": "caderno", "category": "long_term", "text": "prometi devolver o caderno"}]}
    )
    _run_turns(client, session, monkeypatch, 3, utility_reply)

    memory_events = [e for e in sessions.read_events(session["id"]) if e.kind == "memory"]
    assert len(memory_events) == 1
    entries = memory_events[0].payload["entries"]
    assert len(entries) == 1
    assert entries[0]["category"] == "long_term"
    assert entries[0]["text"] == "prometi devolver o caderno"
    assert entries[0]["source"] == "engine"


def test_memory_event_shares_append_events_call_with_rest_of_turn(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_reply = json.dumps(
        {"entries": [{"id": "caderno", "category": "long_term", "text": "prometi devolver"}]}
    )
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _route_by_model(["narra."], utility_reply)
    )

    calls = []
    original = sessions.append_events

    def spy(session_id, events, hud=None):
        calls.append([kind for kind, _ in events])
        return original(session_id, events, hud=hud)

    monkeypatch.setattr(turn, "append_events", spy)

    for _ in range(3):
        _turn(client, session["id"])

    memory_calls = [call for call in calls if "memory" in call]
    assert len(memory_calls) == 1


def test_turn_four_prompt_contains_memories_section(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_reply = json.dumps(
        {"entries": [{"id": "caderno", "category": "long_term", "text": "prometi devolver o caderno"}]}
    )
    _run_turns(client, session, monkeypatch, 3, utility_reply)

    captured = {}
    original_stream = OpenAICompatProvider.stream_chat

    async def capturing_stream(self, messages, model):
        if model == "narrator-model":
            captured["system"] = messages[0].content
        async for delta in original_stream(self, messages, model):
            yield delta

    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _route_by_model(["mais narração."], '{"entries": []}')
    )
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", capturing_stream)

    _turn(client, session["id"])

    assert "## MEMÓRIAS" in captured["system"]
    assert "prometi devolver o caderno" in captured["system"]


def test_session_without_memory_has_no_section(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    captured = {}
    original_stream = OpenAICompatProvider.stream_chat

    async def capturing_stream(self, messages, model):
        if model == "narrator-model":
            captured["system"] = messages[0].content
        async for delta in original_stream(self, messages, model):
            yield delta

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _route_by_model(["narra."], "{}"))
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", capturing_stream)

    _turn(client, session["id"])

    assert "## MEMÓRIAS" not in captured["system"]


def test_invalid_category_from_model_is_rejected(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_reply = json.dumps(
        {"entries": [{"id": "x", "category": "user_note", "text": "nota escrita pelo modelo"}]}
    )
    _run_turns(client, session, monkeypatch, 3, utility_reply)

    memory_events = [e for e in sessions.read_events(session["id"]) if e.kind == "memory"]
    assert memory_events == []


def test_user_note_seeded_appears_last_in_section(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    sessions.append_events(
        session["id"],
        [
            (
                "memory",
                {
                    "entries": [
                        {
                            "id": "nota",
                            "category": "user_note",
                            "text": "nota do jogador",
                            "turn": 1,
                            "source": "player",
                        },
                        {
                            "id": "fato",
                            "category": "long_term",
                            "text": "fato permanente",
                            "turn": 1,
                            "source": "engine",
                        },
                    ]
                },
            )
        ],
    )

    captured = {}
    original_stream = OpenAICompatProvider.stream_chat

    async def capturing_stream(self, messages, model):
        if model == "narrator-model":
            captured["system"] = messages[0].content
        async for delta in original_stream(self, messages, model):
            yield delta

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _route_by_model(["narra."], "{}"))
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", capturing_stream)

    _turn(client, session["id"])

    system = captured["system"]
    assert system.index("fato permanente") < system.index("nota do jogador")


def test_duplicate_proposal_generates_no_event(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    utility_reply = json.dumps(
        {"entries": [{"id": "caderno", "category": "long_term", "text": "prometi devolver o caderno"}]}
    )
    _run_turns(client, session, monkeypatch, 3, utility_reply)
    memory_events_after_first = [e for e in sessions.read_events(session["id"]) if e.kind == "memory"]
    assert len(memory_events_after_first) == 1

    _run_turns(client, session, monkeypatch, 3, utility_reply)
    memory_events_after_second = [e for e in sessions.read_events(session["id"]) if e.kind == "memory"]
    assert len(memory_events_after_second) == 1


def test_category_cap_evicts_fifo_only_from_that_category(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    seeded = [
        {"id": f"g{i}", "category": "goal", "text": f"objetivo {i}", "turn": i, "source": "engine"}
        for i in range(1, 7)
    ] + [{"id": "permanente", "category": "long_term", "text": "fato", "turn": 1, "source": "engine"}]
    sessions.append_events(session["id"], [("memory", {"entries": seeded})])

    utility_reply = json.dumps({"entries": [{"id": "g7", "category": "goal", "text": "objetivo 7"}]})
    _run_turns(client, session, monkeypatch, 3, utility_reply)

    memory_events = [e for e in sessions.read_events(session["id"]) if e.kind == "memory"]
    entries = memory_events[-1].payload["entries"]
    goal_ids = {e["id"] for e in entries if e["category"] == "goal"}
    assert goal_ids == {f"g{i}" for i in range(2, 8)}
    assert any(e["id"] == "permanente" for e in entries)


def test_player_memory_survives_two_extractions(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    sessions.append_events(
        session["id"],
        [
            (
                "memory",
                {
                    "entries": [
                        {
                            "id": "nota",
                            "category": "goal",
                            "text": "nota do jogador",
                            "turn": 1,
                            "source": "player",
                        }
                    ]
                },
            )
        ],
    )

    utility_reply = json.dumps({"entries": [{"id": "nota", "category": "goal", "text": "outra coisa"}]})
    _run_turns(client, session, monkeypatch, 3, utility_reply)
    _run_turns(client, session, monkeypatch, 3, utility_reply)

    memory_events = [e for e in sessions.read_events(session["id"]) if e.kind == "memory"]
    last_entries = memory_events[-1].payload["entries"] if memory_events else []
    note = next((e for e in last_entries if e["id"] == "nota"), None)
    assert note is None or note["text"] == "nota do jogador"


def test_read_memories_survives_corrupted_event(scenarios_root, monkeypatch):
    from app.memory import read_memories

    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    sessions.append_events(
        session["id"],
        [("memory", {"entries": [{"id": "x", "category": "unknown", "text": "y", "turn": 1}]})],
    )
    assert read_memories(session["id"]) == []

    response = client.get(f"/api/sessions/{session['id']}")
    assert response.status_code == 200

    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _route_by_model(["narra."], '{"entries": []}')
    )
    events = _turn(client, session["id"])
    assert events[-1].get("hud") is not None


def test_command_turn_does_not_extract(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    _run_turns(client, session, monkeypatch, 2)

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _route_by_model(["resposta ooc."], "{}")
    )

    with client.stream(
        "POST", f"/api/sessions/{session['id']}/turn", json={"message": "!fofoca"}
    ) as response:
        _stream_events(response)

    assert not any(name == "memories_checked" for name, _ in emitted)


def test_utility_prose_reply_emits_memories_rejected(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    _run_turns(client, session, monkeypatch, 3, "isso não é json, é prosa livre")

    rejected = [props for name, props in emitted if name == "memories_rejected"]
    assert len(rejected) == 1
    assert len(rejected[0]["raw"]) <= 200

    memory_events = [e for e in sessions.read_events(session["id"]) if e.kind == "memory"]
    assert memory_events == []


def test_utility_unavailable_emits_memories_failed(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    async def broken_stream(self, messages, model):
        if model == "utility-model":
            raise RuntimeError("provider unavailable")
            yield ""
        else:
            for delta in ["a narradora fala."]:
                yield delta

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", broken_stream)

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    events = None
    for _ in range(3):
        events = _turn(client, session["id"])

    assert any(name == "memories_failed" for name, _ in emitted)
    assert events[-1].get("hud") is not None


def test_no_utility_role_skips_call(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, config=_config(with_utility=False))
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _route_by_model(["narra."], "{}")
    )
    events = None
    for _ in range(3):
        events = _turn(client, session["id"])

    assert any(name == "memories_failed" for name, _ in emitted)
    assert events[-1].get("hud") is not None


def test_memory_flag_off_disables_everything(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch, flags={"memory": False})
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    called = {"n": 0}

    async def counting_stream(self, messages, model):
        if model == "utility-model":
            called["n"] += 1
            yield '{"entries": []}'
        else:
            for delta in ["narra."]:
                yield delta

    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", counting_stream)

    emitted = []
    monkeypatch.setattr(turn, "emit", lambda event, **props: emitted.append((event, props)))
    for _ in range(3):
        _turn(client, session["id"])

    assert called["n"] == 0
    assert not any(name.startswith("memories_") for name, _ in emitted)
    memory_events = [e for e in sessions.read_events(session["id"]) if e.kind == "memory"]
    assert memory_events == []
