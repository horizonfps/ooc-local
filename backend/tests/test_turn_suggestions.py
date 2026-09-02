import json

import pytest
from fastapi.testclient import TestClient

from app import main, sessions, turn
from app.config import Config
from app.llm.openai_compat import OpenAICompatProvider
from app.prompt import _TEMPLATES

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
suggestions: ["conversar com a Chloe", "ir para a biblioteca", "voltar para casa"]
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
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    return scenario_path


def _config(flags=None):
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "narrator-model"}},
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


def _setup(scenarios_root, monkeypatch, flags=None):
    _write_scenario(scenarios_root)
    config = _config(flags)
    monkeypatch.setattr(main, "load_config", lambda: config)
    monkeypatch.setattr(turn, "load_config", lambda: config)
    return TestClient(main.app)


def _make_fake_stream(text):
    async def fake_stream(self, messages, model):
        yield text

    return fake_stream


def _turn(client, session_id, message="continua"):
    with client.stream(
        "POST", f"/api/sessions/{session_id}/turn", json={"message": message}
    ) as response:
        return _stream_events(response)


def test_three_suggestions_emitted_before_hud_in_order(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    text = (
        "voce anda pelo patio.\n"
        "[SUGGEST:ir para a sala]\n"
        "[SUGGEST:falar com a Chloe]\n"
        "[SUGGEST:sair da escola]"
    )
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(text))

    events = _turn(client, session["id"])

    suggestion_events = [e for e in events if "suggestions" in e]
    assert len(suggestion_events) == 1
    assert suggestion_events[0]["suggestions"] == [
        "ir para a sala",
        "falar com a Chloe",
        "sair da escola",
    ]
    hud_index = next(i for i, e in enumerate(events) if "hud" in e)
    suggestion_index = events.index(suggestion_events[0])
    assert suggestion_index < hud_index

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["turns"][1]["text"] == "voce anda pelo patio."
    assert "[SUGGEST" not in detail["turns"][1]["text"]
    assert detail["suggestions"] == ["ir para a sala", "falar com a Chloe", "sair da escola"]

    narrator_events = [e for e in sessions.read_events(session["id"]) if e.kind == "narrator_turn"]
    assert narrator_events[0].payload["suggestions"] == [
        "ir para a sala",
        "falar com a Chloe",
        "sair da escola",
    ]


def test_session_without_turn_returns_start_suggestions(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    assert session["suggestions"] == [
        "conversar com a Chloe",
        "ir para a biblioteca",
        "voltar para casa",
    ]

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["suggestions"] == [
        "conversar com a Chloe",
        "ir para a biblioteca",
        "voltar para casa",
    ]


def test_four_suggestions_keeps_only_first_three(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    text = (
        "voce anda pelo patio.\n"
        "[SUGGEST:uma]\n"
        "[SUGGEST:duas]\n"
        "[SUGGEST:tres]\n"
        "[SUGGEST:quatro]"
    )
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(text))

    events = _turn(client, session["id"])

    suggestion_event = next(e for e in events if "suggestions" in e)
    assert suggestion_event["suggestions"] == ["uma", "duas", "tres"]


def test_empty_and_too_long_suggestions_are_discarded(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    too_long = "a" * 121
    text = (
        "voce anda pelo patio.\n"
        "[SUGGEST:]\n"
        f"[SUGGEST:{too_long}]\n"
        "[SUGGEST:ir para a sala]"
    )
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(text))

    events = _turn(client, session["id"])

    suggestion_event = next(e for e in events if "suggestions" in e)
    assert suggestion_event["suggestions"] == ["ir para a sala"]

    tag_events = [e for e in sessions.read_events(session["id"]) if e.kind == "tag"]
    suggest_tags = [e for e in tag_events if e.payload["kind"] == "SUGGEST"]
    assert len(suggest_tags) == 3
    assert [t.payload["valid"] for t in suggest_tags] == [False, False, True]


def test_suggestion_with_colon_in_middle_arrives_whole(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    text = "voce anda pelo patio.\n[SUGGEST:Perguntar:onde esta o caderno?]"
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(text))

    events = _turn(client, session["id"])

    suggestion_event = next(e for e in events if "suggestions" in e)
    assert suggestion_event["suggestions"] == ["Perguntar:onde esta o caderno?"]


def test_turn_without_suggest_tags_has_no_sse_event_and_persists_empty_list(
    scenarios_root, monkeypatch
):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    monkeypatch.setattr(
        OpenAICompatProvider, "stream_chat", _make_fake_stream("voce anda pelo patio.")
    )

    events = _turn(client, session["id"])

    assert not any("suggestions" in e for e in events)

    narrator_events = [e for e in sessions.read_events(session["id"]) if e.kind == "narrator_turn"]
    assert narrator_events[0].payload["suggestions"] == []

    detail = client.get(f"/api/sessions/{session['id']}").json()
    assert detail["suggestions"] == []


def test_turn_view_suggestions_and_legacy_event_without_key(scenarios_root, monkeypatch):
    client = _setup(scenarios_root, monkeypatch)
    session = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()
    session_id = session["id"]

    text = "voce anda.\n[SUGGEST:ir para a sala]\n[SUGGEST:falar com a Chloe]\n[SUGGEST:sair]"
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", _make_fake_stream(text))
    _turn(client, session_id)

    detail = client.get(f"/api/sessions/{session_id}").json()
    assert detail["turns"][1]["suggestions"] == ["ir para a sala", "falar com a Chloe", "sair"]

    sessions.append_events(session_id, [("player_turn", {"text": "continua"})])
    sessions.append_events(session_id, [("narrator_turn", {"text": "turno antigo sem chave"})])

    detail2 = client.get(f"/api/sessions/{session_id}").json()
    legacy_turn = detail2["turns"][-1]
    assert legacy_turn["text"] == "turno antigo sem chave"
    assert legacy_turn["suggestions"] == []


def test_format_body_mentions_suggest_in_both_locales():
    assert "[SUGGEST:" in _TEMPLATES["pt-br"]["format_body"]
    assert "[SUGGEST:" in _TEMPLATES["en"]["format_body"]
