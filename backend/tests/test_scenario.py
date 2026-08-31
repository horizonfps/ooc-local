from fastapi.testclient import TestClient

from app import main
from app.hud import hud_from_start
from app.scenario import (
    ScenarioError,
    list_scenarios,
    load_scenario,
    scenarios_dir,
)

WORLD_MD = "# Mundo\n\nUma escola com acentuação:ção, ã, é.\n"

DEFAULT_START = """\
name: Começo
prologue: prologo
opening_scene: cena
hud:
  location: patio
"""

VILLAIN_START = """\
name: Rota vilão
prologue: prologo2
opening_scene: cena2
hud:
  location: sala
  time: "20:00"
  weather: storm
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

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""


def _write_scenario(root, scenario_id, *, scenario_yaml=SCENARIO_YAML, world=WORLD_MD, starts=None, characters=None):
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

    return scenario_path


def test_load_scenario_happy_path_via_dir(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.id == "exemplo-escola"
    assert scenario.meta.name == "Exemplo Escola"
    assert scenario.starts["default"].id == "default"
    assert scenario.characters["chloe"].mind.feeling == "curiosa"
    assert "acentuação" in scenario.world


def test_load_scenario_two_starts_and_default(monkeypatch, tmp_path):
    _write_scenario(
        tmp_path,
        "exemplo-escola",
        starts={"default.yaml": DEFAULT_START, "rota-vilao.yaml": VILLAIN_START},
    )
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert set(scenario.starts) == {"default", "rota-vilao"}
    assert scenario.start().id == "default"


def test_start_characters_none_means_all(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")
    assert scenario.starts["default"].characters is None


def test_start_characters_unknown_id_raises(monkeypatch, tmp_path):
    start_with_unknown = DEFAULT_START + "characters: [ghost]\n"
    _write_scenario(tmp_path, "exemplo-escola", starts={"default.yaml": start_with_unknown})
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    try:
        load_scenario("exemplo-escola")
        assert False, "expected ScenarioError"
    except ScenarioError as exc:
        assert "ghost" in exc.reason


def test_list_scenarios_ignores_file_and_folder_without_scenario_yaml(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola")
    (tmp_path / "README.md").write_text("not a scenario", encoding="utf-8")
    (tmp_path / "empty-folder").mkdir()
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    result = list_scenarios()

    assert [s.id for s in result] == ["exemplo-escola"]


def test_character_unknown_field_raises_scenario_error(monkeypatch, tmp_path):
    bad_character = CHLOE_YAML + "personalidade: typo\n"
    scenario_path = _write_scenario(tmp_path, "exemplo-escola", characters={"chloe.yaml": bad_character})
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    try:
        load_scenario("exemplo-escola")
        assert False, "expected ScenarioError"
    except ScenarioError as exc:
        assert str(scenario_path / "characters" / "chloe.yaml") == str(exc.path)


def test_missing_world_md_raises(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", world=None)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    try:
        load_scenario("exemplo-escola")
        assert False, "expected ScenarioError"
    except ScenarioError:
        pass


def test_load_scenario_not_found_raises(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    try:
        load_scenario("nao-existe")
        assert False, "expected ScenarioError"
    except ScenarioError:
        pass


def test_list_scenarios_skips_invalid_between_valid_and_emits(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "aa-valido")
    _write_scenario(tmp_path, "bb-invalido", world=None)
    _write_scenario(tmp_path, "cc-valido")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    events = []
    monkeypatch.setattr("app.scenario.emit", lambda event, **props: events.append((event, props)))

    result = list_scenarios()

    assert sorted(s.id for s in result) == ["aa-valido", "cc-valido"]
    assert events and events[0][0] == "scenario_invalid"


def test_list_scenarios_empty_root_returns_empty_list(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    assert list_scenarios() == []


def test_list_scenarios_missing_root_returns_empty_without_log(monkeypatch, tmp_path):
    missing_root = tmp_path / "does-not-exist"
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: missing_root)

    events = []
    monkeypatch.setattr("app.scenario.emit", lambda event, **props: events.append((event, props)))

    assert list_scenarios() == []
    assert events == []


def test_hud_from_start_defaults(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")
    hud = hud_from_start(scenario.starts["default"])

    assert hud.turn == 0
    assert hud.location == "patio"
    assert hud.time == "08:00"
    assert hud.weather == "clear"


def test_hud_invalid_time_raises(monkeypatch, tmp_path):
    start = DEFAULT_START.replace("hud:\n  location: patio\n", 'hud:\n  location: patio\n  time: "25:99"\n')
    _write_scenario(tmp_path, "exemplo-escola", starts={"default.yaml": start})
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    try:
        load_scenario("exemplo-escola")
        assert False, "expected ScenarioError"
    except ScenarioError:
        pass


def test_hud_invalid_weather_raises(monkeypatch, tmp_path):
    start = DEFAULT_START.replace("hud:\n  location: patio\n", "hud:\n  location: patio\n  weather: tornado\n")
    _write_scenario(tmp_path, "exemplo-escola", starts={"default.yaml": start})
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    try:
        load_scenario("exemplo-escola")
        assert False, "expected ScenarioError"
    except ScenarioError:
        pass


def test_get_scenarios_route_returns_list(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "bbb-escola", scenario_yaml="name: Bbb\n")
    _write_scenario(tmp_path, "aaa-escola", scenario_yaml="name: Aaa\n")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    client = TestClient(main.app)
    response = client.get("/api/scenarios")

    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body] == ["Aaa", "Bbb"]


def test_get_scenarios_route_empty_root(monkeypatch, tmp_path):
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    client = TestClient(main.app)
    response = client.get("/api/scenarios")
    assert response.status_code == 200
    assert response.json() == []


def test_scenarios_dir_uses_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("OOC_SCENARIOS_DIR", str(tmp_path))
    assert scenarios_dir() == tmp_path
