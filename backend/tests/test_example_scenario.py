import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.hud import WEATHER_CODES
from app.scenario import load_scenario

EXPECTED_CHARACTER_IDS = {"chloe", "ashlee", "mika", "renan", "bia"}

REPO_SCENARIOS = Path(__file__).resolve().parents[2] / "scenarios"


@pytest.fixture(autouse=True)
def _repo_scenarios(monkeypatch):
    monkeypatch.delenv("OOC_SCENARIOS_DIR", raising=False)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: REPO_SCENARIOS)


def test_example_scenario_loads_without_exception():
    scenario = load_scenario("exemplo-escola")
    assert set(scenario.characters.keys()) == EXPECTED_CHARACTER_IDS


def test_example_scenario_default_start_has_valid_weather():
    scenario = load_scenario("exemplo-escola")
    assert scenario.starts["default"].hud.weather in WEATHER_CODES


def test_example_scenario_start_returns_default_without_argument():
    scenario = load_scenario("exemplo-escola")
    assert scenario.start().id == "default"


def test_example_scenario_default_start_explicit_characters():
    scenario = load_scenario("exemplo-escola")
    assert scenario.starts["default"].characters == ["chloe", "ashlee", "mika"]


def test_example_scenario_default_start_has_three_suggestions():
    scenario = load_scenario("exemplo-escola")
    assert len(scenario.starts["default"].suggestions) == 3


def test_example_scenario_characters_have_complete_mind():
    scenario = load_scenario("exemplo-escola")
    for character_id in EXPECTED_CHARACTER_IDS:
        character = scenario.characters[character_id]
        mind = character.mind
        assert mind.feeling
        assert mind.goal
        assert mind.opinion_of_player is not None
        assert mind.secret_plan is not None
        assert len(character.emotions) >= 2
        assert character.emotions[0] == "default"


def test_example_scenario_world_word_count_within_budget():
    scenario = load_scenario("exemplo-escola")
    word_count = len(scenario.world.split())
    assert 250 <= word_count <= 600


def test_example_scenario_prologue_word_count_within_budget():
    scenario = load_scenario("exemplo-escola")
    word_count = len(scenario.starts["default"].prologue.split())
    assert 150 <= word_count <= 300


def test_example_scenario_default_start_conflict_and_mission_word_count_within_budget():
    scenario = load_scenario("exemplo-escola")
    start = scenario.starts["default"]
    assert start.conflict is not None
    assert start.mission is not None
    word_count = len(start.conflict.split()) + len(start.mission.split())
    assert 100 <= word_count <= 300


def test_example_scenario_default_start_conflict_and_mission_present():
    scenario = load_scenario("exemplo-escola")
    start = scenario.starts["default"]
    assert start.conflict is not None
    assert start.mission is not None
    assert len(start.conflict.split()) > 40
    assert len(start.mission.split()) > 40
    assert "Conflito central" not in scenario.world
    assert "Papel do jogador" not in scenario.world
    assert "Tom de narração" in scenario.world
    assert "Regras do mundo" in scenario.world


def test_example_scenario_files_are_utf8_and_accented():
    import app.scenario as scenario_module

    scenario_dir = scenario_module.scenarios_dir() / "exemplo-escola"
    files = [
        scenario_dir / "world.md",
        scenario_dir / "scenario.yaml",
        scenario_dir / "stats.yaml",
        scenario_dir / "commands.yaml",
    ]
    files += sorted((scenario_dir / "starts").glob("*.yaml"))
    files += sorted((scenario_dir / "characters").glob("*.yaml"))
    files += sorted((scenario_dir / "lorebook").glob("*.yaml"))

    accented_chars = set("áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert any(char in accented_chars for char in text), f"{path} has no accented characters"


def test_example_scenario_ignores_env_var_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OOC_SCENARIOS_DIR", str(tmp_path))

    scenario = load_scenario("exemplo-escola")

    assert set(scenario.characters.keys()) == EXPECTED_CHARACTER_IDS


def test_example_scenario_cast_is_larger_than_default_start_cast():
    scenario = load_scenario("exemplo-escola")
    start_characters = set(scenario.starts["default"].characters)
    assert set(scenario.characters.keys()) > start_characters


def test_example_scenario_offscreen_characters_power_tier():
    scenario = load_scenario("exemplo-escola")
    assert scenario.characters["renan"].power_tier == 2
    assert scenario.characters["bia"].power_tier is None


def test_get_scenarios_route_includes_exemplo_escola():
    client = TestClient(main.app)
    response = client.get("/api/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert {"id": "exemplo-escola", "locale": "pt-br"}.items() <= next(
        item for item in body if item["id"] == "exemplo-escola"
    ).items()


def test_example_scenario_stats_ids_and_order():
    scenario = load_scenario("exemplo-escola")
    assert [stat.id for stat in scenario.stats] == ["reputacao", "energia"]


def test_example_scenario_reputacao_range_default_and_levels():
    scenario = load_scenario("exemplo-escola")
    reputacao = next(stat for stat in scenario.stats if stat.id == "reputacao")
    assert reputacao.min == 0
    assert reputacao.max == 100
    assert reputacao.default == 40
    assert [level.from_ for level in reputacao.levels] == [0, 40, 75]


def test_example_scenario_energia_has_no_levels():
    scenario = load_scenario("exemplo-escola")
    energia = next(stat for stat in scenario.stats if stat.id == "energia")
    assert energia.default == 80
    assert energia.levels == []


def test_example_scenario_stats_have_description_icon_and_color():
    scenario = load_scenario("exemplo-escola")
    color_re = re.compile(r"^#[0-9a-fA-F]{6}$")
    for stat in scenario.stats:
        assert stat.description
        assert stat.icon
        assert stat.color
        assert color_re.match(stat.color)


def test_example_scenario_allow_dynamic_stats_is_false():
    scenario = load_scenario("exemplo-escola")
    assert scenario.meta.allow_dynamic_stats is False


def test_example_scenario_reputacao_levels_from_strictly_increasing_within_range():
    scenario = load_scenario("exemplo-escola")
    reputacao = next(stat for stat in scenario.stats if stat.id == "reputacao")
    previous = None
    for level in reputacao.levels:
        assert reputacao.min <= level.from_ <= reputacao.max
        if previous is not None:
            assert level.from_ > previous
        previous = level.from_


def test_example_scenario_lorebook_ids_scope_enabled_and_keywords():
    scenario = load_scenario("exemplo-escola")
    assert set(scenario.lorebook) == {"caderno", "sala-do-gremio"}
    for entry in scenario.lorebook.values():
        assert entry.scope == "keyword"
        assert entry.enabled is True
        assert entry.keywords


def test_example_scenario_caderno_priority_higher_than_sala_do_gremio():
    scenario = load_scenario("exemplo-escola")
    assert scenario.lorebook["caderno"].priority > scenario.lorebook["sala-do-gremio"].priority


def test_example_scenario_lore_body_word_count_within_budget():
    scenario = load_scenario("exemplo-escola")
    for entry in scenario.lorebook.values():
        word_count = len(entry.body.split())
        assert 40 <= word_count <= 200


def test_example_scenario_lore_keywords_are_anchored_in_scenario_text():
    import app.scenario as scenario_module

    scenario = load_scenario("exemplo-escola")
    scenario_dir = scenario_module.scenarios_dir() / "exemplo-escola"

    texts = [(scenario_dir / "world.md").read_text(encoding="utf-8")]
    texts += [path.read_text(encoding="utf-8") for path in sorted((scenario_dir / "starts").glob("*.yaml"))]
    texts += [path.read_text(encoding="utf-8") for path in sorted((scenario_dir / "characters").glob("*.yaml"))]
    haystack = "\n".join(texts).casefold()

    for entry in scenario.lorebook.values():
        if entry.scope != "keyword":
            continue
        assert any(keyword.casefold() in haystack for keyword in entry.keywords)


def test_example_scenario_lorebook_stems_have_no_accent_or_uppercase():
    import app.scenario as scenario_module

    scenario_dir = scenario_module.scenarios_dir() / "exemplo-escola"
    stem_re = re.compile(r"^[a-z0-9-]+$")
    for path in sorted((scenario_dir / "lorebook").glob("*.yaml")):
        assert stem_re.match(path.stem)


def test_example_scenario_commands_include_fofoca():
    scenario = load_scenario("exemplo-escola")
    assert [command.name for command in scenario.commands] == ["fofoca"]
    fofoca = scenario.commands[0]
    assert fofoca.description
    assert fofoca.prompt
    assert "fora da narrativa" in fofoca.prompt.casefold()
