import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import Config

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-data"
JPEG_BYTES = b"\xff\xd8\xff" + b"fake-jpeg-data"
WEBP_BYTES = b"RIFF" + b"\x00\x00\x00\x00" + b"WEBP" + b"fake-webp-data"
TEXT_BYTES = b"this is definitely not an image, just plain text bytes here"


def _config(flags: dict[str, bool] | None = None) -> Config:
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
            "flags": flags or {},
        }
    )


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


def _upload(client, scenario_id, *, kind, key="", character=None, content=PNG_BYTES, filename="upload.png"):
    data = {"kind": kind, "key": key}
    if character is not None:
        data["character"] = character
    files = {"file": (filename, content, "application/octet-stream")}
    return client.post(f"/api/builder/scenarios/{scenario_id}/media", data=data, files=files)


def _delete(client, scenario_id, *, kind, key="", character=None):
    params = {"kind": kind, "key": key}
    if character is not None:
        params["character"] = character
    return client.delete(f"/api/builder/scenarios/{scenario_id}/media", params=params)


def test_upload_cover_sprite_and_background_shows_up_in_index(client, scenarios_root):
    _write_scenario(scenarios_root, "escola")

    cover = _upload(client, "escola", kind="cover")
    assert cover.status_code == 201
    body = cover.json()
    assert body["path"] == "cover.png"
    assert body["url"] == "/api/scenarios/escola/media/cover.png"

    sprite = _upload(client, "escola", kind="sprite", key="default", character="chloe")
    assert sprite.status_code == 201
    assert sprite.json()["path"] == "sprites/chloe/default.png"

    background = _upload(client, "escola", kind="background", key="patio")
    assert background.status_code == 201
    assert background.json()["path"] == "backgrounds/patio.png"

    index = client.get("/api/builder/scenarios/escola/media").json()
    assert index["cover"] == "/api/scenarios/escola/media/cover.png"
    assert index["sprites"] == {"chloe": {"default": "/api/scenarios/escola/media/sprites/chloe/default.png"}}
    assert index["backgrounds"] == {"patio": "/api/scenarios/escola/media/backgrounds/patio.png"}

    for url in [cover.json()["url"], sprite.json()["url"], background.json()["url"]]:
        response = client.get(url)
        assert response.status_code == 200


def test_uploading_twice_to_same_slot_second_content_wins(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")

    first = _upload(client, "escola", kind="sprite", key="default", character="chloe", content=PNG_BYTES)
    assert first.status_code == 201

    second_bytes = b"\x89PNG\r\n\x1a\n" + b"different-content"
    second = _upload(client, "escola", kind="sprite", key="default", character="chloe", content=second_bytes)
    assert second.status_code == 201

    stored = scenario_dir / "media" / "sprites" / "chloe" / "default.png"
    assert stored.read_bytes() == second_bytes
    files = list((scenario_dir / "media" / "sprites" / "chloe").iterdir())
    assert len(files) == 1


def test_delete_removes_file_and_index_entry(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    _upload(client, "escola", kind="sprite", key="default", character="chloe")

    response = _delete(client, "escola", kind="sprite", key="default", character="chloe")
    assert response.status_code == 204
    assert not (scenario_dir / "media" / "sprites" / "chloe" / "default.png").exists()

    index = client.get("/api/builder/scenarios/escola/media").json()
    assert index["sprites"] == {}


def test_webp_signature_is_accepted_and_written_as_webp(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")

    response = _upload(client, "escola", kind="background", key="patio", content=WEBP_BYTES, filename="patio.webp")
    assert response.status_code == 201
    assert response.json()["path"] == "backgrounds/patio.webp"
    assert (scenario_dir / "media" / "backgrounds" / "patio.webp").exists()


def test_replacing_png_with_webp_leaves_only_webp_in_folder(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    _upload(client, "escola", kind="background", key="patio", content=PNG_BYTES)

    response = _upload(client, "escola", kind="background", key="patio", content=WEBP_BYTES, filename="patio.webp")
    assert response.status_code == 201

    backgrounds_dir = scenario_dir / "media" / "backgrounds"
    files = sorted(entry.name for entry in backgrounds_dir.iterdir())
    assert files == ["patio.webp"]


def test_upload_creates_media_tree_when_missing(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    assert not (scenario_dir / "media").exists()

    response = _upload(client, "escola", kind="cover")
    assert response.status_code == 201
    assert (scenario_dir / "media" / "cover.png").exists()


def test_file_too_large_is_413_and_writes_nothing(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    big_content = b"\x89PNG\r\n\x1a\n" + (b"x" * (9 * 1024 * 1024))

    response = _upload(client, "escola", kind="cover", content=big_content)

    assert response.status_code == 413
    assert response.json()["detail"] == "file too large"
    assert not (scenario_dir / "media").exists()


def test_text_renamed_to_png_is_415_and_writes_nothing(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "escola")

    response = _upload(client, "escola", kind="cover", content=TEXT_BYTES, filename="cover.png")

    assert response.status_code == 415
    assert response.json()["detail"] == "unsupported media type"
    assert not (scenario_dir / "media").exists()


def test_key_with_uppercase_is_422(client, scenarios_root):
    _write_scenario(scenarios_root, "escola")

    response = _upload(client, "escola", kind="background", key="Patio")

    assert response.status_code == 422


def test_sprite_without_character_is_422(client, scenarios_root):
    _write_scenario(scenarios_root, "escola")

    response = _upload(client, "escola", kind="sprite", key="default")

    assert response.status_code == 422


def test_background_with_character_is_422(client, scenarios_root):
    _write_scenario(scenarios_root, "escola")

    response = _upload(client, "escola", kind="background", key="patio", character="chloe")

    assert response.status_code == 422


def test_delete_missing_asset_is_404(client, scenarios_root):
    _write_scenario(scenarios_root, "escola")

    response = _delete(client, "escola", kind="background", key="patio")

    assert response.status_code == 404
    assert response.json()["detail"] == "asset not found"


def test_write_failure_is_500_and_emits_media_write_failed(client, scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, "escola")

    events = []
    monkeypatch.setattr("app.media.emit", lambda name, **kw: events.append((name, kw)))
    monkeypatch.setattr("os.replace", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full")))

    response = _upload(client, "escola", kind="cover")

    assert response.status_code == 500
    assert response.json()["detail"] == "write failed"
    assert any(name == "media_write_failed" for name, _ in events)


def test_builder_disabled_by_flag_returns_503_and_disk_untouched(client, scenarios_root, monkeypatch):
    scenario_dir = _write_scenario(scenarios_root, "escola")
    monkeypatch.setattr("app.media.load_config", lambda: _config({"builder": False}))

    post_response = _upload(client, "escola", kind="cover")
    assert post_response.status_code == 503
    assert post_response.json()["detail"] == "builder disabled by flag"
    assert not (scenario_dir / "media").exists()

    delete_response = _delete(client, "escola", kind="cover")
    assert delete_response.status_code == 503
    assert delete_response.json()["detail"] == "builder disabled by flag"


def test_scenario_id_with_traversal_is_404_or_422(client, scenarios_root):
    response = _upload(client, "..%2F..%2Fetc", kind="cover")
    assert response.status_code in (404, 422)
