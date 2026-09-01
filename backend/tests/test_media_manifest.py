import pytest
from fastapi.testclient import TestClient

from app import main
from app.scenario import load_scenario

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-data"

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
locale: pt-br
"""

DEFAULT_START = """\
name: Começo
prologue: prologo default
opening_scene: cena
hud:
  location: patio
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
emotions: [default, sad]
"""

CHLOE_ALT_YAML = """\
name: Chloe
role: aluna
appearance: baixa
personality: extrovertida
voice: animada
mind:
  feeling: curiosa
  goal: descobrir segredo
sprite: chloe-alt
"""


def _write_scenario(root, scenario_id, *, character_yaml=CHLOE_YAML):
    scenario_dir = root / scenario_id
    scenario_dir.mkdir(parents=True)
    (scenario_dir / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_dir / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_dir / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_dir / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(character_yaml, encoding="utf-8")

    return scenario_dir


@pytest.fixture
def scenarios_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OOC_SESSIONS_DB", str(tmp_path / "sessions.db"))
    yield


@pytest.fixture
def client():
    return TestClient(main.app)


def test_session_detail_has_sprite_and_background_manifest(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    sprites_dir = scenario_dir / "media" / "sprites" / "chloe"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "default.png").write_bytes(PNG_BYTES)

    backgrounds_dir = scenario_dir / "media" / "backgrounds"
    backgrounds_dir.mkdir()
    (backgrounds_dir / "patio.png").write_bytes(PNG_BYTES)

    response = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"})
    assert response.status_code == 201
    body = response.json()

    assert body["assets"]["sprites"] == {
        "chloe": {"default": "/api/scenarios/exemplo-escola/media/sprites/chloe/default.png"}
    }
    assert body["assets"]["backgrounds"] == {
        "patio": "/api/scenarios/exemplo-escola/media/backgrounds/patio.png"
    }

    session_id = body["id"]
    get_response = client.get(f"/api/sessions/{session_id}")
    assert get_response.status_code == 200
    assert get_response.json()["assets"] == body["assets"]


def test_asset_urls_download_bytes(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    sprites_dir = scenario_dir / "media" / "sprites" / "chloe"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "default.png").write_bytes(PNG_BYTES)
    backgrounds_dir = scenario_dir / "media" / "backgrounds"
    backgrounds_dir.mkdir()
    (backgrounds_dir / "patio.png").write_bytes(PNG_BYTES)

    body = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    for url in [*body["assets"]["sprites"]["chloe"].values(), *body["assets"]["backgrounds"].values()]:
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == PNG_BYTES


def test_scenario_without_media_returns_empty_dicts(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    response = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"})
    assert response.status_code == 201
    assert response.json()["assets"] == {"sprites": {}, "backgrounds": {}}


def test_character_with_sprite_alias_appears_under_both_keys(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola", character_yaml=CHLOE_ALT_YAML)
    sprites_dir = scenario_dir / "media" / "sprites" / "chloe-alt"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "default.png").write_bytes(PNG_BYTES)

    body = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    expected = {"default": "/api/scenarios/exemplo-escola/media/sprites/chloe-alt/default.png"}
    assert body["assets"]["sprites"]["chloe"] == expected
    assert body["assets"]["sprites"]["chloe-alt"] == expected


def test_orphan_sprite_folder_is_ignored(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    orphan_dir = scenario_dir / "media" / "sprites" / "desconhecido"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "default.png").write_bytes(PNG_BYTES)

    body = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    assert body["assets"]["sprites"] == {}


def test_emotion_declared_without_file_does_not_appear(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    sprites_dir = scenario_dir / "media" / "sprites" / "chloe"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "default.png").write_bytes(PNG_BYTES)

    body = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()

    assert body["assets"]["sprites"]["chloe"] == {
        "default": "/api/scenarios/exemplo-escola/media/sprites/chloe/default.png"
    }
    assert "sad" not in body["assets"]["sprites"]["chloe"]


def test_deleted_scenario_folder_still_returns_404(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    session_id = client.post("/api/sessions", json={"scenarioId": "exemplo-escola"}).json()["id"]

    import shutil

    shutil.rmtree(scenario_dir)

    response = client.get(f"/api/sessions/{session_id}")
    assert response.status_code == 404
    assert response.json()["detail"] == "scenario not found"


def test_session_assets_function_matches_scan(scenarios_root):
    from app.media import session_assets

    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    sprites_dir = scenario_dir / "media" / "sprites" / "chloe"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "default.png").write_bytes(PNG_BYTES)

    scenario = load_scenario("exemplo-escola")
    assets = session_assets(scenario)

    assert assets.sprites == {
        "chloe": {"default": "/api/scenarios/exemplo-escola/media/sprites/chloe/default.png"}
    }
    assert assets.backgrounds == {}
