import pytest

from app.scenario import ScenarioError, load_scenario

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

STATS_TWO = """\
- id: reputacao
  name: Reputação
  min: 0
  max: 100
  default: 50
  description: quão bem visto você é
  levels:
    - from: 0
      text: desconhecido
    - from: 40
      text: conhecido
    - from: 80
      text: famoso
- id: energia
  name: Energia
  min: 0
  max: 10
  default: 5
"""


def _write_scenario(
    root,
    scenario_id,
    *,
    scenario_yaml=SCENARIO_YAML,
    world=WORLD_MD,
    starts=None,
    characters=None,
    stats=None,
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

    if stats is not None:
        (scenario_path / "stats.yaml").write_text(stats, encoding="utf-8")

    return scenario_path


def test_stats_yaml_loads_in_file_order_with_levels_and_description(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", stats=STATS_TWO)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert [stat.id for stat in scenario.stats] == ["reputacao", "energia"]
    assert scenario.stats[0].description == "quão bem visto você é"
    assert [level.from_ for level in scenario.stats[0].levels] == [0, 40, 80]
    assert scenario.stats[0].levels[2].text == "famoso"


def test_allow_dynamic_stats_true_is_read(monkeypatch, tmp_path):
    _write_scenario(
        tmp_path,
        "exemplo-escola",
        scenario_yaml=SCENARIO_YAML + "allow_dynamic_stats: true\n",
    )
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.meta.allow_dynamic_stats is True


def test_allow_dynamic_stats_absent_defaults_false(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.meta.allow_dynamic_stats is False


def test_max_delta_is_read(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", stats="- id: reputacao\n  name: A\n  max: 100\n  default: 0\n  max_delta: 500\n")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.stats[0].max_delta == 500


def test_max_dynamic_stats_is_read(monkeypatch, tmp_path):
    _write_scenario(
        tmp_path, "exemplo-escola", scenario_yaml=SCENARIO_YAML + "max_dynamic_stats: 12\n"
    )
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.meta.max_dynamic_stats == 12


def test_max_delta_and_max_dynamic_stats_absent_are_none(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", stats="- id: reputacao\n  name: A\n  max: 100\n  default: 0\n")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.stats[0].max_delta is None
    assert scenario.meta.max_dynamic_stats is None


def test_max_delta_zero_raises_scenario_error_with_path(monkeypatch, tmp_path):
    _write_scenario(
        tmp_path,
        "exemplo-escola",
        stats="- id: reputacao\n  name: A\n  max: 100\n  default: 0\n  max_delta: 0\n",
    )
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError) as exc_info:
        load_scenario("exemplo-escola")

    assert "stats.yaml" in str(exc_info.value.path)


def test_max_dynamic_stats_zero_raises_scenario_error_with_path(monkeypatch, tmp_path):
    _write_scenario(
        tmp_path, "exemplo-escola", scenario_yaml=SCENARIO_YAML + "max_dynamic_stats: 0\n"
    )
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError) as exc_info:
        load_scenario("exemplo-escola")

    assert "scenario.yaml" in str(exc_info.value.path)


def test_stats_yaml_missing_is_empty_list(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.stats == []


def test_stats_yaml_empty_content_is_empty_list(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", stats="")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    scenario = load_scenario("exemplo-escola")

    assert scenario.stats == []


def test_duplicate_stat_id_raises_scenario_error_with_path(monkeypatch, tmp_path):
    duplicated = """\
- id: reputacao
  name: A
  max: 10
  default: 0
- id: reputacao
  name: B
  max: 10
  default: 0
"""
    _write_scenario(tmp_path, "exemplo-escola", stats=duplicated)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError) as exc_info:
        load_scenario("exemplo-escola")

    assert "stats.yaml" in str(exc_info.value.path)
    assert "duplicate stat id 'reputacao'" in exc_info.value.reason


def test_stats_yaml_as_mapping_raises_scenario_error(monkeypatch, tmp_path):
    _write_scenario(tmp_path, "exemplo-escola", stats="reputacao:\n  max: 10\n")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError) as exc_info:
        load_scenario("exemplo-escola")

    assert "stats.yaml" in str(exc_info.value.path)


@pytest.mark.parametrize(
    "item",
    [
        "- id: rep\n  name: A\n  max: 10\n  min: 10\n  default: 5\n",  # max <= min
        "- id: rep\n  name: A\n  max: 10\n  default: 20\n",  # default out of range
        "- id: rep\n  name: A\n  max: 10\n  default: 5\n  levels:\n"
        "    - from: 5\n      text: a\n    - from: 3\n      text: b\n",  # from not increasing
        "- id: rep\n  name: A\n  max: 10\n  default: 5\n  levels:\n"
        "    - from: 20\n      text: fora\n",  # from out of [min, max]
        "- id: rep\n  name: A\n  max: 10\n  default: 5\n  icon: '12345'\n",  # icon too long
        "- id: rep\n  name: A\n  max: 10\n  default: 5\n  color: 'f5c542'\n",  # color without '#'
        "- id: 'Reputação'\n  name: A\n  max: 10\n  default: 5\n",  # invalid id
        "- id: rep\n  name: A\n  max: 10\n  default: 5\n  unknown: oops\n",  # unknown field
    ],
)
def test_invalid_stat_def_is_rejected(monkeypatch, tmp_path, item):
    _write_scenario(tmp_path, "exemplo-escola", stats=item)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)

    with pytest.raises(ScenarioError):
        load_scenario("exemplo-escola")
