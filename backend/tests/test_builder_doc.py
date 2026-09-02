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


STATS_YAML = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 50
"""

COMMANDS_YAML = """\
- name: fofoca
  description: espalha uma fofoca
  prompt: espalhe uma fofoca
"""

CADERNO_LORE = """\
title: O caderno perdido
keywords: [caderno]
body: um caderno circula pela escola
"""


def _write_scenario(
    root,
    scenario_id,
    *,
    scenario_yaml=SCENARIO_YAML,
    world=WORLD_MD,
    characters=None,
    starts=None,
    stats=None,
    lorebook=None,
    commands=None,
):
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

    if stats is not None:
        (scenario_dir / "stats.yaml").write_text(stats, encoding="utf-8")

    if lorebook is not None:
        lorebook_dir = scenario_dir / "lorebook"
        lorebook_dir.mkdir(exist_ok=True)
        for filename, content in lorebook.items():
            (lorebook_dir / filename).write_text(content, encoding="utf-8")

    if commands is not None:
        (scenario_dir / "commands.yaml").write_text(commands, encoding="utf-8")

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


def test_get_returns_conflict_and_mission_when_present(client, scenarios_root):
    start_with_fields = DEFAULT_START + "conflict: um caderno circula\nmission: descobrir de quem é\n"
    _write_scenario(scenarios_root, "exemplo-escola", starts={"default.yaml": start_with_fields})

    response = client.get("/api/builder/scenarios/exemplo-escola")

    body = response.json()
    assert body["starts"]["default"]["conflict"] == "um caderno circula"
    assert body["starts"]["default"]["mission"] == "descobrir de quem é"


def test_get_returns_null_conflict_and_mission_when_absent(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    response = client.get("/api/builder/scenarios/exemplo-escola")

    body = response.json()
    assert body["starts"]["default"]["conflict"] is None
    assert body["starts"]["default"]["mission"] is None


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


def test_get_returns_stats_lorebook_and_commands_in_file_order(client, scenarios_root):
    _write_scenario(
        scenarios_root,
        "exemplo-escola",
        stats=STATS_YAML,
        lorebook={"caderno.yaml": CADERNO_LORE},
        commands=COMMANDS_YAML,
    )

    response = client.get("/api/builder/scenarios/exemplo-escola")

    body = response.json()
    assert [s["id"] for s in body["stats"]] == ["reputacao"]
    assert set(body["lorebook"]) == {"caderno"}
    assert [c["name"] for c in body["commands"]] == ["fofoca"]


def test_get_without_stats_lorebook_commands_returns_empty(client, scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola")

    response = client.get("/api/builder/scenarios/exemplo-escola")

    body = response.json()
    assert body["stats"] == []
    assert body["lorebook"] == {}
    assert body["commands"] == []


def test_editing_lorebook_file_on_disk_changes_revision(client, scenarios_root):
    scenario_dir = _write_scenario(
        scenarios_root, "exemplo-escola", lorebook={"caderno.yaml": CADERNO_LORE}
    )

    before = compute_revision("exemplo-escola")
    (scenario_dir / "lorebook" / "caderno.yaml").write_text(
        CADERNO_LORE + "priority: 5\n", encoding="utf-8"
    )
    after = compute_revision("exemplo-escola")

    assert before != after


def test_editing_stats_file_on_disk_changes_revision(client, scenarios_root):
    scenario_dir = _write_scenario(scenarios_root, "exemplo-escola", stats=STATS_YAML)

    before = compute_revision("exemplo-escola")
    (scenario_dir / "stats.yaml").write_text(STATS_YAML + "  description: nova\n", encoding="utf-8")
    after = compute_revision("exemplo-escola")

    assert before != after
