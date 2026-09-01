import pytest
from fastapi.testclient import TestClient

from app import main
from app.builder_doc import compute_revision

WORLD_MD = "# Mundo\n\nUma escola com corredores e um jardim.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

DEFAULT_START = """\
name: Começo
prologue: prologo com acentuação
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

MARCO_YAML = """\
name: Marco
role: professor
appearance: alto
personality: sério
voice: grave
mind:
  feeling: cansado
  goal: dar aula
"""

ANA_YAML = """\
name: Ana
role: diretora
appearance: elegante
personality: fria
voice: firme
mind:
  feeling: ocupada
  goal: administrar
"""


def _write_scenario(root, scenario_id, *, scenario_yaml=SCENARIO_YAML, world=WORLD_MD, characters=None, starts=None):
    characters = {
        "chloe.yaml": CHLOE_YAML,
        "marco.yaml": MARCO_YAML,
        "ana.yaml": ANA_YAML,
    } if characters is None else characters
    starts = {"default.yaml": DEFAULT_START} if starts is None else starts

    scenario_dir = root / scenario_id
    scenario_dir.mkdir(parents=True)
    if scenario_yaml is not None:
        (scenario_dir / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    if world is not None:
        (scenario_dir / "world.md").write_text(world, encoding="utf-8")

    starts_dir = scenario_dir / "starts"
    starts_dir.mkdir(exist_ok=True)
    for filename, content in starts.items():
        (starts_dir / filename).write_text(content, encoding="utf-8")

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


def test_full_scenario_returns_document_with_starts_and_characters(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    response = client.get("/api/builder/scenarios/exemplo-escola")

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["name"] == "Exemplo Escola"
    assert len(body["starts"]) == 1
    assert len(body["characters"]) == 3
    assert body["starts"]["default"]["prologue"] == "prologo com acentuação"
    assert body["characters"]["chloe"]["name"] == "Chloe"
    assert "revision" in body and body["revision"]


def test_revision_stable_across_reads(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    first = client.get("/api/builder/scenarios/exemplo-escola").json()["revision"]
    second = client.get("/api/builder/scenarios/exemplo-escola").json()["revision"]

    assert first == second


def test_draft_scenario_without_characters_returns_empty_dict(client, scenarios_root):
    _write_scenario(scenarios_root, "rascunho", characters={})

    response = client.get("/api/builder/scenarios/rascunho")

    assert response.status_code == 200
    assert response.json()["characters"] == {}


def test_scenario_without_world_md_returns_empty_world(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", world=None)

    response = client.get("/api/builder/scenarios/exemplo-escola")

    assert response.status_code == 200
    assert response.json()["world"] == ""


def test_start_with_yml_extension_is_read_with_stem_key(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", starts={"default.yml": DEFAULT_START})

    response = client.get("/api/builder/scenarios/exemplo-escola")

    assert response.status_code == 200
    assert "default" in response.json()["starts"]


def test_rewriting_world_with_same_content_keeps_revision(scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")

    before = compute_revision("exemplo-escola")
    (scenario_dir / "world.md").write_text(WORLD_MD, encoding="utf-8")
    after = compute_revision("exemplo-escola")

    assert before == after


def test_changing_world_content_changes_revision(scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola")

    before = compute_revision("exemplo-escola")
    (scenario_dir / "world.md").write_text(WORLD_MD + "\nMais um paragrafo.\n", encoding="utf-8")
    after = compute_revision("exemplo-escola")

    assert before != after


def test_revision_independent_of_path_separator(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    revision = compute_revision("exemplo-escola")

    assert revision == compute_revision("exemplo-escola")
    assert len(revision) == 16


def test_scenario_yaml_missing_returns_404(client, scenarios_root):
    scenarios_root.mkdir(exist_ok=True)

    response = client.get("/api/builder/scenarios/nao-existe")

    assert response.status_code == 404
    assert response.json()["detail"] == "scenario not found"


def test_scenario_yaml_broken_yaml_returns_422_with_path(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", scenario_yaml="name: [unterminated")

    response = client.get("/api/builder/scenarios/exemplo-escola")

    assert response.status_code == 422
    assert "scenario.yaml" in response.json()["detail"]
    assert "\n" not in response.json()["detail"]


def test_character_with_unknown_field_returns_422_citing_file(client, scenarios_root):
    _write_scenario(
        scenarios_root,
        "exemplo-escola",
        characters={"chloe.yaml": CHLOE_YAML + "unknown_field: oops\n"},
    )

    response = client.get("/api/builder/scenarios/exemplo-escola")

    assert response.status_code == 422
    assert "chloe.yaml" in response.json()["detail"]


def test_duplicate_start_stem_returns_422(client, scenarios_root):
    _write_scenario(
        scenarios_root,
        "exemplo-escola",
        starts={"default.yaml": DEFAULT_START, "default.yml": DEFAULT_START},
    )

    response = client.get("/api/builder/scenarios/exemplo-escola")

    assert response.status_code == 422
    assert "duplicate" in response.json()["detail"]


def test_invalid_scenario_id_returns_422(client, scenarios_root):
    response = client.get("/api/builder/scenarios/.hidden")

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid folder"


def test_traversal_scenario_id_is_404_or_422(client, scenarios_root):
    _write_scenario(scenarios_root, "origem")

    response = client.get("/api/builder/scenarios/../etc")

    assert response.status_code in (404, 422)
    assert not (scenarios_root.parent / "etc").exists()
