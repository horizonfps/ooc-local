import pytest
from fastapi.testclient import TestClient

from app import gallery, main, sessions
from app.scenario import load_scenario

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
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


def _start_yaml(name: str, achievements: list[dict]) -> str:
    lines = [f"name: {name}", "prologue: prologo", "opening_scene: cena", "hud:", "  location: patio"]
    if achievements:
        lines.append("achievements:")
        for a in achievements:
            lines.append(f"  - id: {a['id']}")
            lines.append(f"    name: {a['name']}")
            lines.append(f"    type: {a['type']}")
            lines.append(f"    rarity: {a.get('rarity', 'common')}")
            if a.get("hint") is not None:
                lines.append(f"    hint: {a['hint']}")
            lines.append(f"    condition: {a.get('condition', 'sempre')}")
    return "\n".join(lines) + "\n"


def _write_scenario(root, scenario_id="exemplo-escola", starts: dict[str, list[dict]] | None = None):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    starts = starts or {"default": []}
    for start_id, achievements in starts.items():
        (starts_dir / f"{start_id}.yaml").write_text(_start_yaml(f"Começo {start_id}", achievements), encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")
    return scenario_path


def _achievement_event(id_, name, type_, rarity, turn, text="marco atingido"):
    payload = {"id": id_, "type": type_, "rarity": rarity, "name": name, "turn": turn}
    if text is not None:
        payload["text"] = text
    return ("achievement", payload)


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


def test_route_returns_separated_lists_with_correct_totals(scenarios_root):
    _write_scenario(
        scenarios_root,
        starts={
            "default": [
                {"id": "primeira-alianca", "name": "Escolhi um lado", "type": "achievement", "rarity": "rare"},
                {"id": "segunda", "name": "Segunda conquista", "type": "achievement"},
                {"id": "caderno-queimado", "name": "Ninguem mais le isso", "type": "ending", "rarity": "legendary"},
            ]
        },
    )
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(detail.id, [_achievement_event("primeira-alianca", "x", "achievement", "rare", 7)])

    client = TestClient(main.app)
    response = client.get("/api/scenarios/exemplo-escola/gallery")
    assert response.status_code == 200
    body = response.json()

    assert body["scenarioId"] == "exemplo-escola"
    start = body["starts"][0]
    assert [a["id"] for a in start["achievements"]] == ["primeira-alianca", "segunda"]
    assert [e["id"] for e in start["endings"]] == ["caderno-queimado"]

    unlocked = start["achievements"][0]
    assert unlocked["unlocked"] is True
    assert unlocked["sessionId"] == detail.id
    assert unlocked["turn"] == 7
    assert unlocked["unlockedAt"] is not None

    not_unlocked = start["achievements"][1]
    assert not_unlocked["unlocked"] is False
    assert not_unlocked["unlockedAt"] is None
    assert not_unlocked["sessionId"] is None
    assert not_unlocked["turn"] is None

    assert body["totals"] == {
        "achievements": 2,
        "achievementsUnlocked": 1,
        "endings": 1,
        "endingsUnlocked": 0,
    }


def test_build_gallery_pure_with_hand_built_unlocks(scenarios_root):
    _write_scenario(
        scenarios_root,
        starts={"default": [{"id": "a1", "name": "A1", "type": "achievement"}]},
    )
    scenario = load_scenario("exemplo-escola")
    unlocks = [
        sessions.ScenarioUnlock(
            start_id="default", session_id="s1", id="a1", turn=3, created_at="2026-01-01T00:00:00.000Z"
        )
    ]

    result = gallery.build_gallery(scenario, unlocks)

    assert result.starts[0].achievements[0].unlocked is True
    assert result.starts[0].achievements[0].session_id == "s1"
    assert result.totals.achievements_unlocked == 1


def test_older_unlock_wins_when_two_sessions_unlock_the_same_id(scenarios_root):
    _write_scenario(
        scenarios_root,
        starts={"default": [{"id": "a1", "name": "A1", "type": "achievement"}]},
    )
    session1 = sessions.create_session("exemplo-escola")
    session2 = sessions.create_session("exemplo-escola")

    sessions.append_events(session2.id, [_achievement_event("a1", "A1", "achievement", "common", 5)])
    sessions.append_events(session1.id, [_achievement_event("a1", "A1", "achievement", "common", 2)])

    # session2's event was written first, so it has the older created_at.
    result = gallery.build_gallery(load_scenario("exemplo-escola"), sessions.read_scenario_unlocks("exemplo-escola"))
    entry = result.starts[0].achievements[0]
    assert entry.unlocked is True
    assert entry.session_id == session2.id
    assert entry.turn == 5


def test_unlock_in_other_start_does_not_mark_this_start(scenarios_root):
    _write_scenario(
        scenarios_root,
        starts={
            "default": [{"id": "shared", "name": "Shared", "type": "achievement"}],
            "alt": [{"id": "shared", "name": "Shared", "type": "achievement"}],
        },
    )
    detail = sessions.create_session("exemplo-escola", start_id="default")
    sessions.append_events(detail.id, [_achievement_event("shared", "Shared", "achievement", "common", 1)])

    result = gallery.build_gallery(load_scenario("exemplo-escola"), sessions.read_scenario_unlocks("exemplo-escola"))
    by_id = {start.id: start for start in result.starts}
    assert by_id["default"].achievements[0].unlocked is True
    assert by_id["alt"].achievements[0].unlocked is False


def test_entry_follows_declared_type_even_when_event_type_differs(scenarios_root):
    _write_scenario(
        scenarios_root,
        starts={"default": [{"id": "e1", "name": "E1", "type": "ending"}]},
    )
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(detail.id, [_achievement_event("e1", "E1", "achievement", "common", 1)])

    result = gallery.build_gallery(load_scenario("exemplo-escola"), sessions.read_scenario_unlocks("exemplo-escola"))
    start = result.starts[0]
    assert start.achievements == []
    assert start.endings[0].unlocked is True


def test_ephemeral_session_unlock_does_not_count(scenarios_root):
    _write_scenario(
        scenarios_root,
        starts={"default": [{"id": "a1", "name": "A1", "type": "achievement"}]},
    )
    detail = sessions.create_session("exemplo-escola", ephemeral=True)
    sessions.append_events(detail.id, [_achievement_event("a1", "A1", "achievement", "common", 1)])

    result = gallery.build_gallery(load_scenario("exemplo-escola"), sessions.read_scenario_unlocks("exemplo-escola"))
    assert result.starts[0].achievements[0].unlocked is False


def test_unlock_for_id_no_longer_declared_does_not_appear(scenarios_root):
    _write_scenario(
        scenarios_root,
        starts={"default": [{"id": "a1", "name": "A1", "type": "achievement"}]},
    )
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(
        detail.id,
        [
            _achievement_event("a1", "A1", "achievement", "common", 1),
            _achievement_event("removida", "Removida", "achievement", "common", 2),
        ],
    )

    result = gallery.build_gallery(load_scenario("exemplo-escola"), sessions.read_scenario_unlocks("exemplo-escola"))
    ids = [entry.id for entry in result.starts[0].achievements]
    assert ids == ["a1"]


def test_scenario_without_achievements_returns_empty_lists_and_zero_totals(scenarios_root):
    _write_scenario(scenarios_root, starts={"default": []})

    client = TestClient(main.app)
    response = client.get("/api/scenarios/exemplo-escola/gallery")
    assert response.status_code == 200
    body = response.json()
    assert body["starts"][0]["achievements"] == []
    assert body["starts"][0]["endings"] == []
    assert body["totals"] == {
        "achievements": 0,
        "achievementsUnlocked": 0,
        "endings": 0,
        "endingsUnlocked": 0,
    }


def test_malformed_payload_is_skipped_and_route_still_returns_200(scenarios_root):
    _write_scenario(
        scenarios_root,
        starts={"default": [{"id": "a1", "name": "A1", "type": "achievement"}]},
    )
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(
        detail.id,
        [("achievement", {"type": "achievement", "rarity": "common", "name": "sem id", "turn": 1, "text": "x"})],
    )

    client = TestClient(main.app)
    response = client.get("/api/scenarios/exemplo-escola/gallery")
    assert response.status_code == 200
    assert response.json()["starts"][0]["achievements"][0]["unlocked"] is False


def test_nonexistent_scenario_returns_404(scenarios_root):
    client = TestClient(main.app)
    response = client.get("/api/scenarios/does-not-exist/gallery")
    assert response.status_code == 404
    assert response.json()["detail"] == "scenario not found"


def test_invalid_scenario_id_returns_422(scenarios_root):
    client = TestClient(main.app)
    response = client.get("/api/scenarios/.hidden/gallery")
    assert response.status_code == 422
    assert response.json()["detail"] == "invalid folder"
