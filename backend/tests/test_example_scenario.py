from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import main
from app.hud import WEATHER_CODES
from app.scenario import load_scenario

EXPECTED_CHARACTER_IDS = {"chloe", "ashlee", "mika"}

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
        mind = scenario.characters[character_id].mind
        assert mind.feeling
        assert mind.goal
        assert mind.opinion_of_player is not None
        assert mind.secret_plan is not None


def test_example_scenario_world_word_count_within_budget():
    scenario = load_scenario("exemplo-escola")
    word_count = len(scenario.world.split())
    assert 300 <= word_count <= 600


def test_example_scenario_prologue_word_count_within_budget():
    scenario = load_scenario("exemplo-escola")
    word_count = len(scenario.starts["default"].prologue.split())
    assert 150 <= word_count <= 300


def test_example_scenario_files_are_utf8_and_accented():
    import app.scenario as scenario_module

    scenario_dir = scenario_module.scenarios_dir() / "exemplo-escola"
    files = [scenario_dir / "world.md", scenario_dir / "scenario.yaml"]
    files += sorted((scenario_dir / "starts").glob("*.yaml"))
    files += sorted((scenario_dir / "characters").glob("*.yaml"))

    accented_chars = set("áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ")
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert any(char in accented_chars for char in text), f"{path} has no accented characters"


def test_example_scenario_ignores_env_var_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OOC_SCENARIOS_DIR", str(tmp_path))

    scenario = load_scenario("exemplo-escola")

    assert set(scenario.characters.keys()) == EXPECTED_CHARACTER_IDS


def test_get_scenarios_route_includes_exemplo_escola():
    client = TestClient(main.app)
    response = client.get("/api/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert {"id": "exemplo-escola", "locale": "pt-br"}.items() <= next(
        item for item in body if item["id"] == "exemplo-escola"
    ).items()
