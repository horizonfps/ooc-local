import os
import time

import pytest
import yaml
from fastapi.testclient import TestClient

from app import main
from app.scenario import load_scenario

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

DEFAULT_START = """\
name: Começo
prologue: prologo
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
"""


def _write_scenario(root, scenario_id, *, scenario_yaml=SCENARIO_YAML, world=WORLD_MD, characters=None):
    characters = {"chloe.yaml": CHLOE_YAML} if characters is None else characters

    scenario_dir = root / scenario_id
    scenario_dir.mkdir(parents=True)
    if scenario_yaml is not None:
        (scenario_dir / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    if world is not None:
        (scenario_dir / "world.md").write_text(world, encoding="utf-8")

    starts_dir = scenario_dir / "starts"
    starts_dir.mkdir(exist_ok=True)
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_dir / "characters"
    characters_dir.mkdir(exist_ok=True)
    for filename, content in characters.items():
        (characters_dir / filename).write_text(content, encoding="utf-8")

    return scenario_dir


@pytest.fixture
def scenarios_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def client():
    return TestClient(main.app)


def test_create_then_list_shows_ok_item(client, scenarios_root):
    response = client.post(
        "/api/builder/scenarios",
        json={"folder": "nova-escola", "name": "Nova Escola", "locale": "pt-br"},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["id"] == "nova-escola"
    assert created["status"] == "ok"
    assert created["startCount"] == 1
    assert created["characterCount"] == 0

    listed = client.get("/api/builder/scenarios").json()
    assert [item["id"] for item in listed] == ["nova-escola"]
    assert listed[0]["startCount"] == 1
    assert listed[0]["characterCount"] == 0

    with pytest.raises(Exception):
        load_scenario("nova-escola")


def test_duplicate_copies_media_bytes(client, scenarios_root):
    source = _write_scenario(scenarios_root, "origem")
    backgrounds = source / "media" / "backgrounds"
    backgrounds.mkdir(parents=True)
    payload = b"\x89PNG-fake-bytes"
    (backgrounds / "patio.png").write_bytes(payload)

    response = client.post("/api/builder/scenarios/origem/duplicate", json={"folder": "copia"})

    assert response.status_code == 201
    copied_file = scenarios_root / "copia" / "media" / "backgrounds" / "patio.png"
    assert copied_file.exists()
    assert copied_file.read_bytes() == payload

    loaded = load_scenario("copia")
    assert loaded.meta.name == "Exemplo Escola"


def test_delete_removes_folder_and_listing_entry(client, scenarios_root):
    _write_scenario(scenarios_root, "para-deletar")

    response = client.delete("/api/builder/scenarios/para-deletar")

    assert response.status_code == 204
    assert not (scenarios_root / "para-deletar").exists()
    assert client.get("/api/builder/scenarios").json() == []


def test_broken_scenario_yaml_is_invalid_but_does_not_break_listing(client, scenarios_root):
    _write_scenario(scenarios_root, "boa")
    broken_dir = scenarios_root / "quebrada"
    broken_dir.mkdir()
    (broken_dir / "scenario.yaml").write_text("name: [unterminated", encoding="utf-8")

    listed = client.get("/api/builder/scenarios").json()

    by_id = {item["id"]: item for item in listed}
    assert by_id["boa"]["status"] == "ok"
    assert by_id["quebrada"]["status"] == "invalid"
    assert by_id["quebrada"]["reason"]


def test_scenario_valid_with_empty_characters_dir_is_ok(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "sem-elenco", characters={})

    listed = client.get("/api/builder/scenarios").json()

    item = next(item for item in listed if item["id"] == "sem-elenco")
    assert item["status"] == "ok"
    assert item["characterCount"] == 0


def test_updated_at_changes_after_rewriting_world_md(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "muda-mundo")

    before = client.get("/api/builder/scenarios").json()[0]["updatedAt"]

    time.sleep(0.02)
    os.utime(scenario_dir / "world.md", None)
    (scenario_dir / "world.md").write_text(WORLD_MD + "\nmais texto\n", encoding="utf-8")

    after = client.get("/api/builder/scenarios").json()[0]["updatedAt"]

    assert after != before


def test_post_with_slug_containing_space_is_422(client, scenarios_root):
    response = client.post(
        "/api/builder/scenarios",
        json={"folder": "Pasta Com Espaço", "name": "X", "locale": "pt-br"},
    )

    assert response.status_code == 422
    assert response.json() == {"detail": "invalid folder"}
    assert list(scenarios_root.iterdir()) == []


def test_post_existing_folder_is_409_and_leaves_it_untouched(client, scenarios_root):
    _write_scenario(scenarios_root, "ja-existe")
    original_mtime = (scenarios_root / "ja-existe" / "scenario.yaml").stat().st_mtime

    response = client.post(
        "/api/builder/scenarios",
        json={"folder": "ja-existe", "name": "Outro Nome", "locale": "pt-br"},
    )

    assert response.status_code == 409
    assert (scenarios_root / "ja-existe" / "scenario.yaml").stat().st_mtime == original_mtime


def test_duplicate_traversal_source_id_is_404_or_422(client, scenarios_root):
    _write_scenario(scenarios_root, "origem")

    response = client.post("/api/builder/scenarios/../etc/duplicate", json={"folder": "copia"})

    assert response.status_code in (404, 422)
    assert not (scenarios_root.parent / "etc").exists()
    assert [entry.name for entry in scenarios_root.iterdir()] == ["origem"]


def test_delete_rmtree_oserror_is_500_and_folder_stays(client, scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, "protegida")

    def _boom(path):
        raise OSError("permission denied")

    monkeypatch.setattr("app.builder.shutil.rmtree", _boom)

    response = client.delete("/api/builder/scenarios/protegida")

    assert response.status_code == 500
    assert response.json() == {"detail": "delete failed"}
    assert (scenarios_root / "protegida").exists()


def test_no_tmp_folder_left_after_create(client, scenarios_root):
    client.post(
        "/api/builder/scenarios",
        json={"folder": "limpa", "name": "Limpa", "locale": "en"},
    )

    entries = [entry.name for entry in scenarios_root.iterdir()]
    assert entries == ["limpa"]


def test_no_tmp_folder_left_after_failed_create(client, scenarios_root, monkeypatch):
    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.builder.os.replace", _boom)

    response = client.post(
        "/api/builder/scenarios",
        json={"folder": "falha", "name": "Falha", "locale": "en"},
    )

    assert response.status_code == 500
    assert list(scenarios_root.iterdir()) == []
