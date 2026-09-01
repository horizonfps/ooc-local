import pytest
from fastapi.testclient import TestClient

from app import main
from app.builder_doc import compute_revision
from app.config import Config

WORLD_MD = "# Mundo\n\nUma escola com corredores e um jardim.\n"

# Written already in canonical (post-write_document) form so a no-op
# GET -> PUT round trip produces byte-identical files.
SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
world_mode: guided
tags: []
default_start: default
"""

DEFAULT_START = """\
name: Começo
prologue: prologo com acentuação
opening_scene: cena
suggestions: []
hud:
  location: patio
  time: 08:00
  weather: clear
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
emotions:
- default
"""


def _write_scenario(root, scenario_id, *, scenario_yaml=SCENARIO_YAML, world=WORLD_MD, characters=None, starts=None):
    characters = {"chloe.yaml": CHLOE_YAML} if characters is None else characters
    starts = {"default.yaml": DEFAULT_START} if starts is None else starts

    scenario_dir = root / scenario_id
    scenario_dir.mkdir(parents=True)
    if scenario_yaml is not None:
        (scenario_dir / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8", newline="\n")
    if world is not None:
        (scenario_dir / "world.md").write_text(world, encoding="utf-8", newline="\n")

    starts_dir = scenario_dir / "starts"
    starts_dir.mkdir(exist_ok=True)
    for filename, content in starts.items():
        (starts_dir / filename).write_text(content, encoding="utf-8", newline="\n")

    characters_dir = scenario_dir / "characters"
    characters_dir.mkdir(exist_ok=True)
    for filename, content in characters.items():
        (characters_dir / filename).write_text(content, encoding="utf-8", newline="\n")

    return scenario_dir


@pytest.fixture
def scenarios_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def client():
    return TestClient(main.app)


def _config(flags: dict[str, bool] | None = None) -> Config:
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
            "flags": flags or {},
        }
    )


def test_put_with_correct_revision_saves_and_returns_new_revision(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    doc["meta"]["name"] = "Nova Escola"
    doc["starts"]["default"]["prologue"] = "prologo novo"

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    new_revision = response.json()["revision"]
    assert new_revision != doc["revision"]

    reread = client.get("/api/builder/scenarios/exemplo-escola").json()
    assert reread["meta"]["name"] == "Nova Escola"
    assert reread["starts"]["default"]["prologue"] == "prologo novo"
    assert reread["revision"] == new_revision


def test_put_adding_character_writes_file_with_canonical_order_and_accents(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    doc["characters"]["nova"] = {
        "name": "Nova",
        "role": "aluna nova",
        "appearance": "cabelo cacheado, uso de óculos",
        "personality": "tímida",
        "voice": "baixinha",
        "mind": {"feeling": "ansiosa", "goal": "se encaixar"},
        "sprite": None,
        "power_tier": 1,
        "emotions": ["default"],
    }

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    nova_path = scenario_dir / "characters" / "nova.yaml"
    assert nova_path.exists()
    lines = nova_path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "name: Nova"
    assert lines[1].startswith("role:")
    assert "óculos" in nova_path.read_text(encoding="utf-8")


def test_put_writes_conflict_and_mission_in_canonical_order(client, scenarios_root):
    scenario_dir = _write_scenario(
        scenarios_root,
        "exemplo-escola",
        starts={"default.yaml": DEFAULT_START + "play_guide: guia do start\n"},
    )
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    doc["starts"]["default"]["conflict"] = "um caderno circula"
    doc["starts"]["default"]["mission"] = "descobrir de quem é"

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    lines = (scenario_dir / "starts" / "default.yaml").read_text(encoding="utf-8").splitlines()
    opening_scene_index = next(i for i, line in enumerate(lines) if line.startswith("opening_scene:"))
    conflict_index = next(i for i, line in enumerate(lines) if line.startswith("conflict:"))
    mission_index = next(i for i, line in enumerate(lines) if line.startswith("mission:"))
    play_guide_index = next(i for i, line in enumerate(lines) if line.startswith("play_guide:"))
    assert opening_scene_index < conflict_index < mission_index < play_guide_index


def test_put_with_only_conflict_writes_that_key_alone(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    doc["starts"]["default"]["conflict"] = "um caderno circula"
    doc["starts"]["default"]["mission"] = None

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    lines = (scenario_dir / "starts" / "default.yaml").read_text(encoding="utf-8").splitlines()
    assert any(line.startswith("conflict:") for line in lines)
    assert not any(line.startswith("mission:") for line in lines)
    reread = client.get("/api/builder/scenarios/exemplo-escola").json()
    assert reread["starts"]["default"]["conflict"] == "um caderno circula"
    assert reread["starts"]["default"]["mission"] is None


def test_put_with_blank_conflict_and_mission_omits_keys_and_get_returns_null(client, scenarios_root):
    scenario_dir = _write_scenario(
        scenarios_root,
        "exemplo-escola",
        starts={"default.yaml": DEFAULT_START + "play_guide: guia do start\n"},
    )
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    doc["starts"]["default"]["conflict"] = ""
    doc["starts"]["default"]["mission"] = ""

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    text = (scenario_dir / "starts" / "default.yaml").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert not any(line.startswith("conflict:") for line in lines)
    assert not any(line.startswith("mission:") for line in lines)

    reread = client.get("/api/builder/scenarios/exemplo-escola").json()
    assert reread["starts"]["default"]["conflict"] is None
    assert reread["starts"]["default"]["mission"] is None


def test_put_identical_document_does_not_change_revision_or_mtime(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    meta_before = (scenario_dir / "scenario.yaml").stat().st_mtime_ns
    start_before = (scenario_dir / "starts" / "default.yaml").stat().st_mtime_ns
    char_before = (scenario_dir / "characters" / "chloe.yaml").stat().st_mtime_ns

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    assert response.json()["revision"] == doc["revision"]
    assert (scenario_dir / "scenario.yaml").stat().st_mtime_ns == meta_before
    assert (scenario_dir / "starts" / "default.yaml").stat().st_mtime_ns == start_before
    assert (scenario_dir / "characters" / "chloe.yaml").stat().st_mtime_ns == char_before


def test_put_with_stale_revision_returns_409_and_disk_untouched(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()
    before = (scenario_dir / "world.md").read_bytes()

    (scenario_dir / "world.md").write_text(WORLD_MD + "editado por fora\n", encoding="utf-8")

    doc["meta"]["name"] = "Tentativa de sobrescrever"
    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 409
    assert response.json()["detail"] == "revision conflict"
    assert (scenario_dir / "world.md").read_bytes() != before

    doc["force"] = True
    forced = client.put("/api/builder/scenarios/exemplo-escola", json=doc)
    assert forced.status_code == 200

    reread = client.get("/api/builder/scenarios/exemplo-escola").json()
    assert reread["meta"]["name"] == "Tentativa de sobrescrever"


def test_put_removes_start_missing_from_payload_and_adds_new_one(client, scenarios_root):
    scenario_dir = _write_scenario(
        scenarios_root,
        "exemplo-escola",
        starts={"default.yaml": DEFAULT_START, "extra.yaml": DEFAULT_START},
    )
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()
    assert set(doc["starts"]) == {"default", "extra"}

    del doc["starts"]["extra"]
    doc["starts"]["novo"] = dict(doc["starts"]["default"])

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    assert not (scenario_dir / "starts" / "extra.yaml").exists()
    assert (scenario_dir / "starts" / "novo.yaml").exists()


def test_put_with_unknown_default_start_returns_422_and_does_not_write(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()
    before = (scenario_dir / "scenario.yaml").read_bytes()

    doc["meta"]["default_start"] = "nao-existe"

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 422
    assert (scenario_dir / "scenario.yaml").read_bytes() == before


def test_get_put_get_roundtrip_without_changes_keeps_revision(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    first = client.get("/api/builder/scenarios/exemplo-escola").json()
    put_response = client.put("/api/builder/scenarios/exemplo-escola", json=first)
    second = client.get("/api/builder/scenarios/exemplo-escola").json()

    assert put_response.json()["revision"] == first["revision"]
    assert second["revision"] == first["revision"]


def test_put_disabled_by_flag_returns_503_and_writes_nothing(client, scenarios_root, monkeypatch):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()
    before = (scenario_dir / "scenario.yaml").read_bytes()

    monkeypatch.setattr("app.builder_doc.load_config", lambda: _config({"builder": False}))
    doc["meta"]["name"] = "Nunca deveria salvar"

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 503
    assert response.json()["detail"] == "builder disabled by flag"
    assert (scenario_dir / "scenario.yaml").read_bytes() == before


def test_put_empty_world_writes_empty_file_and_reads_back_empty(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    doc["world"] = ""
    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    reread = client.get("/api/builder/scenarios/exemplo-escola").json()
    assert reread["world"] == ""


def test_put_start_saved_with_yml_and_yaml_leaves_only_yaml(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola", starts={"default.yml": DEFAULT_START})
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    assert (scenario_dir / "starts" / "default.yaml").exists()
    assert not (scenario_dir / "starts" / "default.yml").exists()


def test_put_normalizes_emotions_order_before_writing(client, scenarios_root):
    scenario_dir = _write_scenario(
        scenarios_root,
        "exemplo-escola",
        characters={"chloe.yaml": CHLOE_YAML + "emotions: [smile, default, sad]\n"},
    )
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()
    assert doc["characters"]["chloe"]["emotions"] == ["default", "smile", "sad"]

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 200
    content = (scenario_dir / "characters" / "chloe.yaml").read_text(encoding="utf-8")
    assert "emotions" in content


def test_put_with_invalid_start_key_returns_422(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    default_start = doc["starts"].pop("default")
    doc["starts"]["Start Um"] = default_start
    doc["meta"]["default_start"] = "Start Um"

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 422


def test_put_with_no_starts_returns_422(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()

    doc["starts"] = {}

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 422


def test_put_os_replace_failure_returns_500_and_emits_event(client, scenarios_root, monkeypatch):
    _write_scenario(scenarios_root, "exemplo-escola")
    doc = client.get("/api/builder/scenarios/exemplo-escola").json()
    doc["meta"]["name"] = "Vai falhar"

    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "app.builder_doc.emit",
        lambda event, **props: events.append((event, props)),
    )

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.builder_doc.os.replace", _boom)

    response = client.put("/api/builder/scenarios/exemplo-escola", json=doc)

    assert response.status_code == 500
    assert response.json()["detail"] == "write failed"
    assert any(event == "builder_doc_write_failed" for event, _ in events)
