import pytest

from app.scenario import ScenarioError, list_scenarios, load_scenario

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

CADERNO_LORE = """\
title: O caderno perdido
keywords: [caderno, diario]
body: um caderno circula pela escola
"""

REGRAS_LORE = """\
title: Regras da escola
body: proibido correr no corredor
scope: always
"""

FOFOCA_COMMAND = """\
- name: fofoca
  description: espalha uma fofoca
  prompt: espalhe uma fofoca sobre o personagem atual
"""


def _write_scenario(
    root,
    scenario_id,
    *,
    scenario_yaml=SCENARIO_YAML,
    world=WORLD_MD,
    starts=None,
    characters=None,
    lorebook=None,
    commands=None,
):
    starts = {"default.yaml": DEFAULT_START} if starts is None else starts
    characters = {"chloe.yaml": CHLOE_YAML} if characters is None else characters

    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    if scenario_yaml is not None:
        (scenario_path / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    if world is not None:
        (scenario_path / "world.md").write_text(world, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir(exist_ok=True)
    for filename, content in starts.items():
        (starts_dir / filename).write_text(content, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir(exist_ok=True)
    for filename, content in characters.items():
        (characters_dir / filename).write_text(content, encoding="utf-8")

    if lorebook is not None:
        lorebook_dir = scenario_path / "lorebook"
        lorebook_dir.mkdir(exist_ok=True)
        for filename, content in lorebook.items():
            (lorebook_dir / filename).write_text(content, encoding="utf-8")

    if commands is not None:
        (scenario_path / "commands.yaml").write_text(commands, encoding="utf-8")

    return scenario_path


def test_lorebook_entries_load_as_dict_by_stem_with_defaults(monkeypatch, tmp_path):
    _write_scenario(
        tmp_path,
        "exemplo-escola",
        lorebook={"caderno.yaml": CADERNO_LORE, "regras.yaml": REGRAS_LORE},
    )
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert set(scenario.lorebook) == {"caderno", "regras"}
    assert scenario.lorebook["caderno"].scope == "keyword"
    assert scenario.lorebook["caderno"].priority == 0
    assert scenario.lorebook["caderno"].enabled is True
    assert scenario.lorebook["regras"].scope == "always"


def test_commands_yaml_loads_name_description_prompt(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", commands=FOFOCA_COMMAND)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert len(scenario.commands) == 1
    assert scenario.commands[0].name == "fofoca"
    assert scenario.commands[0].description == "espalha uma fofoca"
    assert scenario.commands[0].prompt == "espalhe uma fofoca sobre o personagem atual"


def test_lorebook_dir_missing_is_empty_dict(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.lorebook == {}


def test_lorebook_dir_empty_is_empty_dict(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", lorebook={})
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.lorebook == {}


def test_commands_yaml_missing_is_empty_list(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.commands == []


def test_lore_entry_scope_always_with_no_keywords_is_accepted(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", lorebook={"regras.yaml": REGRAS_LORE})
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.lorebook["regras"].keywords == []


def test_lore_entry_scope_keyword_without_keywords_raises(monkeypatch, tmp_path):
    bad_lore = "title: Sem palavra-chave\nbody: texto\n"
    _write_scenario(tmp_path, "exemplo-escola", lorebook={"vazio.yaml": bad_lore})
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError):
        load_scenario("exemplo-escola")


def test_lorebook_stem_uppercase_is_rejected(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", lorebook={"Caderno.yaml": CADERNO_LORE})
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError):
        load_scenario("exemplo-escola")


def test_lorebook_same_stem_in_yaml_and_yml_raises(monkeypatch, tmp_path):
    _write_scenario(
        tmp_path,
        "exemplo-escola",
        lorebook={"caderno.yaml": CADERNO_LORE, "caderno.yml": CADERNO_LORE},
    )
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError):
        load_scenario("exemplo-escola")


def test_duplicate_command_name_raises(monkeypatch, tmp_path):
    duplicated = """\
- name: fofoca
  description: A
  prompt: a
- name: fofoca
  description: B
  prompt: b
"""
    _write_scenario(tmp_path, "exemplo-escola", commands=duplicated)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError) as exc_info:
        load_scenario("exemplo-escola")

    assert "commands.yaml" in str(exc_info.value.path)
    assert "duplicate command name 'fofoca'" in exc_info.value.reason


def test_command_name_with_space_is_rejected(monkeypatch, tmp_path):
    bad_command = "- name: 'fofoca boa'\n  description: A\n  prompt: a\n"
    _write_scenario(tmp_path, "exemplo-escola", commands=bad_command)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError):
        load_scenario("exemplo-escola")


def test_list_scenarios_with_broken_stats_yaml_emits_and_skips(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "aa-valido")
    _write_scenario(tmp_path, "bb-invalido")
    (tmp_path / "bb-invalido" / "stats.yaml").write_text("reputacao:\n  max: 10\n", encoding="utf-8")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    events = []
    monkeypatch.setattr("app.scenario.emit", lambda event, **props: events.append((event, props)))

    result = list_scenarios()

    assert [s.id for s in result] == ["aa-valido"]
    assert events and events[0][0] == "scenario_invalid"
