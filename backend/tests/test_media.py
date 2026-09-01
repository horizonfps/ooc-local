import pytest
from fastapi.testclient import TestClient

from app import main

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-data"


def _write_scenario(root, scenario_id):
    scenario_dir = root / scenario_id
    scenario_dir.mkdir(parents=True)
    (scenario_dir / "scenario.yaml").write_text("name: Exemplo\nlocale: pt-br\n", encoding="utf-8")
    return scenario_dir


@pytest.fixture
def scenarios_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def client():
    return TestClient(main.app)


def test_index_lists_cover_sprites_and_backgrounds(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    media_dir = scenario_dir / "media"
    (media_dir).mkdir()
    (media_dir / "cover.png").write_bytes(PNG_BYTES)

    sprites_dir = media_dir / "sprites" / "chloe"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "default.png").write_bytes(PNG_BYTES)
    (sprites_dir / "sad.png").write_bytes(PNG_BYTES)

    backgrounds_dir = media_dir / "backgrounds"
    backgrounds_dir.mkdir()
    (backgrounds_dir / "patio.png").write_bytes(PNG_BYTES)

    response = client.get("/api/builder/scenarios/escola/media")
    assert response.status_code == 200
    body = response.json()
    assert body["cover"] == "/api/scenarios/escola/media/cover.png"
    assert body["sprites"] == {
        "chloe": {
            "default": "/api/scenarios/escola/media/sprites/chloe/default.png",
            "sad": "/api/scenarios/escola/media/sprites/chloe/sad.png",
        }
    }
    assert body["backgrounds"] == {"patio": "/api/scenarios/escola/media/backgrounds/patio.png"}


def test_download_each_url_returns_bytes(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    media_dir = scenario_dir / "media"
    media_dir.mkdir()
    (media_dir / "cover.png").write_bytes(PNG_BYTES)
    sprites_dir = media_dir / "sprites" / "chloe"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "default.png").write_bytes(PNG_BYTES)
    backgrounds_dir = media_dir / "backgrounds"
    backgrounds_dir.mkdir()
    (backgrounds_dir / "patio.png").write_bytes(PNG_BYTES)

    index = client.get("/api/builder/scenarios/escola/media").json()

    for url in [index["cover"], *index["sprites"]["chloe"].values(), *index["backgrounds"].values()]:
        response = client.get(url)
        assert response.status_code == 200
        assert response.content == PNG_BYTES
        assert response.headers["cache-control"] == "no-cache"


def test_uppercase_filename_is_ignored(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    sprites_dir = scenario_dir / "media" / "sprites" / "chloe"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "Sad.PNG").write_bytes(PNG_BYTES)

    response = client.get("/api/builder/scenarios/escola/media")
    assert response.status_code == 200
    body = response.json()
    assert body["sprites"] == {}


def test_scenario_without_media_folder_returns_empty_index(client, scenarios_root):
    _write_scenario(scenarios_root, "escola")

    response = client.get("/api/builder/scenarios/escola/media")
    assert response.status_code == 200
    assert response.json() == {"cover": None, "sprites": {}, "backgrounds": {}}


def test_scenario_with_empty_media_folder_returns_empty_index(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    (scenario_dir / "media").mkdir()

    response = client.get("/api/builder/scenarios/escola/media")
    assert response.status_code == 200
    assert response.json() == {"cover": None, "sprites": {}, "backgrounds": {}}


def test_png_and_jpg_in_same_slot_resolves_to_png(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    sprites_dir = scenario_dir / "media" / "sprites" / "chloe"
    sprites_dir.mkdir(parents=True)
    (sprites_dir / "default.png").write_bytes(PNG_BYTES)
    (sprites_dir / "default.jpg").write_bytes(PNG_BYTES)

    response = client.get("/api/builder/scenarios/escola/media")
    body = response.json()
    assert body["sprites"]["chloe"]["default"] == "/api/scenarios/escola/media/sprites/chloe/default.png"


@pytest.mark.parametrize(
    "path",
    [
        "../scenario.yaml",
        "cover.yaml",
    ],
)
def test_file_route_rejects_traversal_and_bad_extension(client, scenarios_root, path):
    _write_scenario(scenarios_root, "escola")

    response = client.get(f"/api/scenarios/escola/media/{path}")
    assert response.status_code == 404


def test_file_route_rejects_backslash_traversal(client, scenarios_root):
    _write_scenario(scenarios_root, "escola")

    response = client.get("/api/scenarios/escola/media/sprites%5C..%5C..%5Cscenario.yaml")
    assert response.status_code == 404


def test_file_route_rejects_directory(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    backgrounds_dir = scenario_dir / "media" / "backgrounds"
    backgrounds_dir.mkdir(parents=True)

    response = client.get("/api/scenarios/escola/media/backgrounds")
    assert response.status_code == 404


def test_scenario_id_with_traversal_is_404_on_both_routes(client, scenarios_root):
    response = client.get("/api/builder/scenarios/..%2F..%2Fetc/media")
    assert response.status_code in (404, 422)

    response = client.get("/api/scenarios/..%2F..%2Fetc/media/cover.png")
    assert response.status_code in (404, 422)


def test_unknown_scenario_returns_404(client, scenarios_root):
    response = client.get("/api/builder/scenarios/inexistente/media")
    assert response.status_code == 404
