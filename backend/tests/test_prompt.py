from __future__ import annotations

import re

from app.hud import WEATHER_CODES, HudState
from app.prompt import WEATHER_LABELS, build_master_prompt
from app.scenario import load_scenario

WORLD_MD = "# Mundo\n\nUma escola nas montanhas.\n"

SCENARIO_YAML_PTBR = """\
name: Exemplo Escola
tagline: uma tagline
locale: pt-br
"""

SCENARIO_YAML_EN = """\
name: Example School
tagline: a tagline
locale: en
"""

DEFAULT_START = """\
name: Começo
prologue: prologo
opening_scene: Você acorda no dormitório.
hud:
  location: dormitorio
  time: "08:00"
  weather: clear
"""

CHLOE_YAML = """\
name: Chloe
role: aluna
appearance: baixa, cabelo curto
personality: extrovertida
voice: animada
mind:
  feeling: curiosa
  goal: descobrir segredo
  opinion_of_player: acha o jogador estranho
  secret_plan: pretende fugir da escola
"""

MARCO_YAML = """\
name: Marco
role: professor
appearance: alto, óculos
personality: sério
voice: grave
mind:
  feeling: cansado
  goal: manter a ordem
"""


def _write_scenario(root, scenario_id, *, scenario_yaml, characters):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    for filename, content in characters.items():
        (characters_dir / filename).write_text(content, encoding="utf-8")

    return scenario_path


def _load(monkeypatch, tmp_path, *, locale="pt-br", characters=None):
    scenario_yaml = SCENARIO_YAML_PTBR if locale == "pt-br" else SCENARIO_YAML_EN
    characters = characters or {"chloe.yaml": CHLOE_YAML, "marco.yaml": MARCO_YAML}
    _write_scenario(tmp_path, "exemplo-escola", scenario_yaml=scenario_yaml, characters=characters)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return load_scenario("exemplo-escola")


def _hud() -> HudState:
    return HudState(turn=3, location="patio", time="09:30", weather="cloudy")


def test_build_master_prompt_ptbr_happy_path(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    headers = [
        "## NARRADOR",
        "## MUNDO",
        "## PERSONAGENS EM CENA",
        "## ESTADO DO JOGO",
        "## CENA DE ABERTURA",
        "## FORMATO DO TURNO",
    ]
    positions = [prompt.index(h) for h in headers]
    assert positions == sorted(positions)
    assert "## RESUMO DA CAMPANHA" not in prompt

    assert "#### Mundo" in prompt
    assert "Uma escola nas montanhas." in prompt
    assert "Chloe" in prompt
    assert "Marco" in prompt
    assert "aluna" in prompt
    assert "extrovertida" in prompt

    assert "Turno: 3" in prompt
    assert "Local: patio" in prompt
    assert "Hora: 09:30" in prompt
    assert "Clima: Nublado" in prompt
    assert "Clima: cloudy" not in prompt

    assert "350 palavras" in prompt
    assert "**Nome** | fala" in prompt
    assert "[LOC:" in prompt


def test_build_master_prompt_en_locale(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en")
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "## NARRATOR" in prompt
    assert "## WORLD" in prompt
    assert "## CHARACTERS IN SCENE" in prompt
    assert "## GAME STATE" in prompt
    assert "## OPENING SCENE" in prompt
    assert "## TURN FORMAT" in prompt
    assert "350 words" in prompt
    assert "**Name** | line" in prompt
    assert "Weather: Cloudy" in prompt
    assert "[LOC:" in prompt

    for word in ["NARRADOR", "MUNDO", "PERSONAGENS", "FORMATO DO TURNO"]:
        assert word not in prompt


def test_build_master_prompt_compact_present_and_absent(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    with_compact = build_master_prompt(
        scenario, start, _hud(), characters, compact="resumo dos ultimos turnos"
    )
    assert "## RESUMO DA CAMPANHA" in with_compact
    assert "resumo dos ultimos turnos" in with_compact

    without_compact = build_master_prompt(scenario, start, _hud(), characters, compact=None)
    assert "## RESUMO DA CAMPANHA" not in without_compact


def test_build_master_prompt_character_optional_fields_omitted(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, characters={"marco.yaml": MARCO_YAML})
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "None" not in prompt


def test_build_master_prompt_no_characters_in_scene(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()

    prompt = build_master_prompt(scenario, start, _hud(), [])

    assert "## PERSONAGENS EM CENA" in prompt
    assert "Nenhum NPC em cena no momento." in prompt


def test_build_master_prompt_is_deterministic(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    first = build_master_prompt(scenario, start, _hud(), characters, compact="resumo")
    second = build_master_prompt(scenario, start, _hud(), characters, compact="resumo")

    assert first == second


def test_build_master_prompt_trusts_hud_state(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    # HudState schema already validates weather; this test documents that
    # build_master_prompt trusts whatever HudState instance it receives.
    hud = HudState(turn=0, location="patio", time="08:00", weather="clear")
    prompt = build_master_prompt(scenario, start, hud, characters)

    assert "Clima: Limpo" in prompt


def test_build_master_prompt_weather_table_matches_codes():
    for locale in ("pt-br", "en"):
        assert set(WEATHER_LABELS[locale]) == set(WEATHER_CODES)


def test_build_master_prompt_unknown_weather_code_falls_back_raw(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    # model_construct bypasses validation: the prompt must survive codes that
    # HudState itself rejects (TCK-019 validators)
    hud = HudState.model_construct(turn=3, location="patio", time="09:30", weather="chuvisco")
    prompt = build_master_prompt(scenario, start, hud, characters)

    assert "Clima: chuvisco" in prompt


def test_build_master_prompt_world_heading_does_not_create_false_boundary(monkeypatch, tmp_path):
    world_md = "## ESTADO DO JOGO\n\nConteudo do autor.\n"
    characters = {"chloe.yaml": CHLOE_YAML, "marco.yaml": MARCO_YAML}
    _write_scenario(tmp_path, "exemplo-escola", scenario_yaml=SCENARIO_YAML_PTBR, characters=characters)
    (tmp_path / "exemplo-escola" / "world.md").write_text(world_md, encoding="utf-8")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    scenario = load_scenario("exemplo-escola")
    start = scenario.start()
    loaded_characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), loaded_characters)

    assert len(re.findall(r"(?m)^## ESTADO DO JOGO$", prompt)) == 1
    assert len(re.findall(r"(?m)^### ", prompt)) == len(loaded_characters)


def test_build_master_prompt_heading_saturates_at_six(monkeypatch, tmp_path):
    world_md = "###### Nota\n\nTexto.\n"
    characters = {"chloe.yaml": CHLOE_YAML}
    _write_scenario(tmp_path, "exemplo-escola", scenario_yaml=SCENARIO_YAML_PTBR, characters=characters)
    (tmp_path / "exemplo-escola" / "world.md").write_text(world_md, encoding="utf-8")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    scenario = load_scenario("exemplo-escola")
    start = scenario.start()
    loaded_characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), loaded_characters)

    assert "###### Nota" in prompt
    assert "######### Nota" not in prompt


def test_build_master_prompt_non_heading_lines_untouched(monkeypatch, tmp_path):
    world_md = "#semespaco linha\ncódigo # dentro da linha\n"
    characters = {"chloe.yaml": CHLOE_YAML}
    _write_scenario(tmp_path, "exemplo-escola", scenario_yaml=SCENARIO_YAML_PTBR, characters=characters)
    (tmp_path / "exemplo-escola" / "world.md").write_text(world_md, encoding="utf-8")
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    scenario = load_scenario("exemplo-escola")
    start = scenario.start()
    loaded_characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), loaded_characters)

    assert "#semespaco linha" in prompt
    assert "código # dentro da linha" in prompt


def test_build_master_prompt_opening_scene_without_heading_untouched(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "Você acorda no dormitório." in prompt


def test_build_master_prompt_no_neutralized_output_produces_reserved_headings():
    from app.prompt import _neutralize_headings

    sample = (
        "# Um\n"
        "## Dois\n"
        "### Tres\n"
        "###### Seis\n"
        "#semespaco\n"
        "texto normal\n"
    )
    output = _neutralize_headings(sample)
    assert not re.search(r"(?m)^(##|###)[ \t]", output)
