import pytest
from fastapi.testclient import TestClient

from app import main, sessions
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


def _config(flags: dict[str, bool] | None = None) -> Config:
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
            "flags": flags or {},
        }
    )


def _achievement_event(id_, name, type_, rarity, turn, text="marco atingido"):
    payload = {"id": id_, "type": type_, "rarity": rarity, "name": name, "turn": turn}
    if text is not None:
        payload["text"] = text
    return ("achievement", payload)


def test_achievement_and_ending_appear_in_achievements_and_turns(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        [
            ("player_turn", {"text": "eu ando"}),
            ("narrator_turn", {"text": "voce anda", "suggestions": []}),
            _achievement_event("primeira-alianca", "Escolhi um lado", "achievement", "rare", 1),
        ],
    )
    sessions.append_events(
        detail.id,
        [
            ("player_turn", {"text": "eu termino"}),
            ("narrator_turn", {"text": "fim", "suggestions": []}),
            _achievement_event("caderno-queimado", "Caderno queimado", "ending", "epic", 2),
            ("session_ended", {"achievement_id": "caderno-queimado", "turn": 2}),
        ],
    )

    result = sessions.get_session(detail.id)

    assert [a.id for a in result.achievements] == ["primeira-alianca", "caderno-queimado"]
    assert result.ended is True

    milestones = [t for t in result.turns if t.kind == "milestone"]
    epilogues = [t for t in result.turns if t.kind == "epilogue"]
    assert len(milestones) == 1
    assert milestones[0].achievement.id == "primeira-alianca"
    assert milestones[0].role == "narrator"
    assert milestones[0].index == 1
    assert len(epilogues) == 1
    assert epilogues[0].achievement.id == "caderno-queimado"


def test_full_cycle_end_reject_reopen_accept(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    monkeypatch.setattr(main, "load_config", lambda: _config())

    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(detail.id, [("session_ended", {"achievement_id": "x", "turn": 0})])

    client = TestClient(main.app)
    response = client.post(f"/api/sessions/{detail.id}/turn", json={"message": "oi"})
    assert response.status_code == 409
    assert response.json()["detail"] == "session ended"

    reopened = client.post(f"/api/sessions/{detail.id}/reopen")
    assert reopened.status_code == 200
    assert reopened.json()["ended"] is False

    response2 = client.post(f"/api/sessions/{detail.id}/turn", json={"message": "oi"})
    assert response2.status_code != 409


def test_reopened_without_ended_before_is_not_ended_and_reopen_rejects(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(detail.id, [("session_reopened", {"turn": 0})])

    assert sessions.is_session_ended(detail.id) is False

    with pytest.raises(sessions.SessionNotEnded):
        sessions.reopen_session(detail.id)


def test_duplicate_achievement_ids_keep_first_occurrence(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        [_achievement_event("dup", "Primeiro", "achievement", "rare", 1, text="primeiro texto")],
    )
    sessions.append_events(
        detail.id,
        [_achievement_event("dup", "Segundo", "achievement", "epic", 2, text="segundo texto")],
    )

    result = sessions.read_achievements(detail.id)
    assert len(result) == 1
    assert result[0].name == "Primeiro"
    assert result[0].rarity == "rare"


def test_achievement_without_text_has_no_turn_but_appears_in_achievements(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        [_achievement_event("sem-texto", "Sem texto", "achievement", "common", 1, text=None)],
    )
    sessions.append_events(
        detail.id,
        [_achievement_event("texto-vazio", "Texto vazio", "achievement", "common", 2, text="")],
    )

    result = sessions.get_session(detail.id)
    assert [a.id for a in result.achievements] == ["sem-texto", "texto-vazio"]
    assert result.turns == []


def test_flag_off_allows_turn_and_reopen_still_works(scenarios_root, monkeypatch):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")
    sessions.append_events(detail.id, [("session_ended", {"achievement_id": "x", "turn": 0})])

    monkeypatch.setattr(main, "load_config", lambda: _config({"achievements": False}))
    client = TestClient(main.app)

    response = client.post(f"/api/sessions/{detail.id}/turn", json={"message": "oi"})
    assert response.status_code != 409

    reopened = client.post(f"/api/sessions/{detail.id}/reopen")
    assert reopened.status_code == 200


def test_malformed_achievement_payloads_are_ignored(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    sessions.append_events(
        detail.id,
        [
            ("achievement", {"type": "achievement", "rarity": "rare", "name": "sem id", "turn": 1, "text": "x"}),
            ("achievement", {"id": "turn-invalido", "type": "achievement", "rarity": "rare", "name": "n", "turn": "abc", "text": "x"}),
            _achievement_event("valido", "Valido", "achievement", "rare", 1),
        ],
    )

    result = sessions.read_achievements(detail.id)
    assert [a.id for a in result] == ["valido"]


def test_reopen_nonexistent_session_returns_404_and_writes_nothing(scenarios_root):
    _write_scenario(scenarios_root)
    client = TestClient(main.app)
    response = client.post("/api/sessions/does-not-exist/reopen")
    assert response.status_code == 404


def test_reopen_session_that_is_not_ended_returns_409(scenarios_root):
    _write_scenario(scenarios_root)
    detail = sessions.create_session("exemplo-escola")

    client = TestClient(main.app)
    response = client.post(f"/api/sessions/{detail.id}/reopen")
    assert response.status_code == 409
    assert response.json()["detail"] == "session is not ended"
