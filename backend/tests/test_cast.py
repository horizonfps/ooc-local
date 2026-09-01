import pytest

from app import sessions
from app.cast import (
    MAX_CAST_IN_SCENE,
    cast_event,
    resolve_cast,
    seed_cast_ids,
    validate_cast_ids,
)
from app.scenario import load_scenario

WORLD_MD = "# Mundo\n\nUma escola.\n"

SCENARIO_YAML = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
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

MIKA_YAML = """\
name: Mika
role: aluna
appearance: alta
personality: reservada
voice: baixa
mind:
  feeling: cautelosa
  goal: proteger amigos
"""

ASHLEE_YAML = """\
name: Ashlee
role: professora
appearance: elegante
personality: severa
voice: firme
mind:
  feeling: cansada
  goal: manter a ordem
"""


def _default_start(characters_yaml: str | None) -> str:
    base = """\
name: Comeco
prologue: prologo default
opening_scene: cena
hud:
  location: patio
"""
    if characters_yaml is None:
        return base
    return base + characters_yaml


def _write_scenario(root, scenario_id, *, characters_line=None, characters=None):
    starts = {"default.yaml": _default_start(characters_line)}
    characters = (
        {"chloe.yaml": CHLOE_YAML, "mika.yaml": MIKA_YAML, "ashlee.yaml": ASHLEE_YAML}
        if characters is None
        else characters
    )

    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(SCENARIO_YAML, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    for filename, content in starts.items():
        (starts_dir / filename).write_text(content, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    for filename, content in characters.items():
        (characters_dir / filename).write_text(content, encoding="utf-8")

    return scenario_path


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("OOC_SESSIONS_DB", str(tmp_path / "sessions.db"))
    yield


@pytest.fixture
def scenarios_root(tmp_path, monkeypatch):
    root = tmp_path / "scenarios"
    root.mkdir()
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: root)
    return root


def test_seed_cast_ids_with_explicit_characters(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe, mika]\n")
    scenario = load_scenario("exemplo-escola")
    start = scenario.start()

    assert seed_cast_ids(scenario, start) == ["chloe", "mika"]

    members = resolve_cast(scenario, seed_cast_ids(scenario, start))
    assert [m.name for m in members] == ["Chloe", "Mika"]


def test_api_reads_seed_then_last_cast_event(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe]\n")
    created = sessions.create_session("exemplo-escola")
    assert [m.id for m in created.cast] == ["chloe"]

    sessions.append_events(created.id, [cast_event(["mika"], "director")])
    reopened = sessions.get_session(created.id)
    assert [m.id for m in reopened.cast] == ["mika"]


def test_last_cast_event_wins_over_earlier_ones(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe]\n")
    created = sessions.create_session("exemplo-escola")

    sessions.append_events(created.id, [cast_event(["mika"], "director")])
    sessions.append_events(created.id, [cast_event(["chloe", "ashlee"], "director")])

    reopened = sessions.get_session(created.id)
    assert [m.id for m in reopened.cast] == ["chloe", "ashlee"]


def test_characters_null_seeds_whole_cast(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line=None)
    scenario = load_scenario("exemplo-escola")
    start = scenario.start()

    assert seed_cast_ids(scenario, start) == ["ashlee", "chloe", "mika"]


def test_characters_empty_list_seeds_empty_cast_via_api(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: []\n")
    created = sessions.create_session("exemplo-escola")
    assert created.cast == []

    reopened = sessions.get_session(created.id)
    assert reopened.cast == []


def test_validate_cast_ids_dedupes_in_order(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe]\n")
    scenario = load_scenario("exemplo-escola")

    assert validate_cast_ids(scenario, ["chloe", "chloe"]) == (["chloe"], None)


def test_validate_cast_ids_over_cap(scenarios_root):
    _write_scenario(
        scenarios_root,
        "exemplo-escola",
        characters_line=None,
        characters={
            "c1.yaml": CHLOE_YAML,
            "c2.yaml": CHLOE_YAML,
            "c3.yaml": CHLOE_YAML,
            "c4.yaml": CHLOE_YAML,
            "c5.yaml": CHLOE_YAML,
            "c6.yaml": CHLOE_YAML,
            "c7.yaml": CHLOE_YAML,
        },
    )
    scenario = load_scenario("exemplo-escola")
    assert len(scenario.characters) == 7

    ids = list(scenario.characters)
    assert MAX_CAST_IN_SCENE == 6
    assert validate_cast_ids(scenario, ids) == (None, "over_cap")


@pytest.mark.parametrize("bad", [["chloe", 3], "chloe", None, {"scene": []}])
def test_validate_cast_ids_not_a_list(scenarios_root, bad):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe]\n")
    scenario = load_scenario("exemplo-escola")

    assert validate_cast_ids(scenario, bad) == (None, "not_a_list")


def test_validate_cast_ids_unknown_ids(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe]\n")
    scenario = load_scenario("exemplo-escola")

    assert validate_cast_ids(scenario, ["fantasma"]) == (None, "unknown_ids")


def test_validate_cast_ids_empty_list_is_valid(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe]\n")
    scenario = load_scenario("exemplo-escola")

    assert validate_cast_ids(scenario, []) == ([], None)


def test_resolve_cast_ignores_unknown_id(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe]\n")
    scenario = load_scenario("exemplo-escola")

    members = resolve_cast(scenario, ["fantasma", "chloe"])
    assert [m.id for m in members] == ["chloe"]


def test_corrupted_cast_event_without_ids_falls_back_to_seed(scenarios_root):
    _write_scenario(scenarios_root, "exemplo-escola", characters_line="characters: [chloe]\n")
    created = sessions.create_session("exemplo-escola")

    sessions.append_events(created.id, [("cast", {"source": "director"})])

    assert sessions.read_cast_ids(created.id) is None

    reopened = sessions.get_session(created.id)
    assert [m.id for m in reopened.cast] == ["chloe"]
