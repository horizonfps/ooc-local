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

MARCO_WITH_TIER_YAML = """\
name: Marco
role: professor
appearance: alto, óculos
personality: sério
voice: grave
power_tier: 3
mind:
  feeling: cansado
  goal: manter a ordem
"""

CHLOE_WITH_EMOTIONS_YAML = """\
name: Chloe
role: aluna
appearance: baixa, cabelo curto
personality: extrovertida
voice: animada
emotions: [sad, angry, smile]
mind:
  feeling: curiosa
  goal: descobrir segredo
"""


def _write_scenario(root, scenario_id, *, scenario_yaml, characters, start=DEFAULT_START):
    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(start, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    for filename, content in characters.items():
        (characters_dir / filename).write_text(content, encoding="utf-8")

    return scenario_path


def _load(monkeypatch, tmp_path, *, locale="pt-br", characters=None, start=DEFAULT_START):
    scenario_yaml = SCENARIO_YAML_PTBR if locale == "pt-br" else SCENARIO_YAML_EN
    characters = characters or {"chloe.yaml": CHLOE_YAML, "marco.yaml": MARCO_YAML}
    _write_scenario(tmp_path, "exemplo-escola", scenario_yaml=scenario_yaml, characters=characters, start=start)
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


def test_build_master_prompt_tag_vocabulary_ptbr(monkeypatch, tmp_path):
    scenario = _load(
        monkeypatch,
        tmp_path,
        characters={"chloe.yaml": CHLOE_WITH_EMOTIONS_YAML, "marco.yaml": MARCO_YAML},
    )
    backgrounds_dir = tmp_path / "exemplo-escola" / "media" / "backgrounds"
    backgrounds_dir.mkdir(parents=True)
    (backgrounds_dir / "patio-da-escola.png").write_bytes(b"fake")
    (backgrounds_dir / "sala-de-aula.png").write_bytes(b"fake")

    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "## VOCABULÁRIO DE TAGS" in prompt
    assert "chloe: default, sad, angry, smile" in prompt
    assert "marco:" not in prompt
    assert "Backgrounds disponíveis: patio-da-escola, sala-de-aula" in prompt
    assert "Use somente estas chaves" in prompt


def test_build_master_prompt_tag_vocabulary_en(monkeypatch, tmp_path):
    scenario = _load(
        monkeypatch,
        tmp_path,
        locale="en",
        characters={"chloe.yaml": CHLOE_WITH_EMOTIONS_YAML, "marco.yaml": MARCO_YAML},
    )
    backgrounds_dir = tmp_path / "exemplo-escola" / "media" / "backgrounds"
    backgrounds_dir.mkdir(parents=True)
    (backgrounds_dir / "patio-da-escola.png").write_bytes(b"fake")

    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "## TAG VOCABULARY" in prompt
    assert "chloe: default, sad, angry, smile" in prompt
    assert "Available backgrounds: patio-da-escola" in prompt


def test_build_master_prompt_tag_vocabulary_omitted_when_empty(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "## VOCABULÁRIO DE TAGS" not in prompt


def test_build_master_prompt_tag_vocabulary_sprites_only(monkeypatch, tmp_path):
    scenario = _load(
        monkeypatch,
        tmp_path,
        characters={"chloe.yaml": CHLOE_WITH_EMOTIONS_YAML, "marco.yaml": MARCO_YAML},
    )
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "## VOCABULÁRIO DE TAGS" in prompt
    assert "chloe: default, sad, angry, smile" in prompt
    assert "Backgrounds disponíveis" not in prompt


def test_build_master_prompt_tag_vocabulary_backgrounds_only(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    backgrounds_dir = tmp_path / "exemplo-escola" / "media" / "backgrounds"
    backgrounds_dir.mkdir(parents=True)
    (backgrounds_dir / "patio-da-escola.png").write_bytes(b"fake")

    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "## VOCABULÁRIO DE TAGS" in prompt
    assert "Backgrounds disponíveis: patio-da-escola" in prompt
    assert "Emoções por personagem" not in prompt


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


def test_build_master_prompt_roster_ptbr_happy_path(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    chloe = scenario.characters["chloe"]

    prompt = build_master_prompt(scenario, start, _hud(), [chloe])

    characters_section, _, rest = prompt.partition("## ESTADO DO JOGO")
    assert "## ELENCO FORA DE CENA" in characters_section
    roster_section = characters_section.split("## ELENCO FORA DE CENA", 1)[1]
    assert "Marco" in roster_section
    assert "professor" in roster_section
    assert "cansado" not in roster_section
    assert "manter a ordem" not in roster_section


def test_build_master_prompt_roster_en_happy_path(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en")
    start = scenario.start()
    chloe = scenario.characters["chloe"]

    prompt = build_master_prompt(scenario, start, _hud(), [chloe])

    assert "## CAST OFF SCENE" in prompt
    assert "ELENCO" not in prompt
    assert "PERSONAGENS" not in prompt


def test_build_master_prompt_roster_absent_when_all_in_scene(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "## ELENCO FORA DE CENA" not in prompt


def test_build_master_prompt_roster_tier_shown_only_when_present(monkeypatch, tmp_path):
    scenario = _load(
        monkeypatch,
        tmp_path,
        characters={"chloe.yaml": CHLOE_YAML, "marco.yaml": MARCO_WITH_TIER_YAML},
    )
    start = scenario.start()
    chloe = scenario.characters["chloe"]

    prompt = build_master_prompt(scenario, start, _hud(), [chloe])

    assert "(tier 3)" in prompt
    assert "None" not in prompt

    no_tier_path = tmp_path / "no-tier"
    no_tier_path.mkdir()
    scenario_no_tier = _load(monkeypatch, no_tier_path)
    start_no_tier = scenario_no_tier.start()
    chloe_no_tier = scenario_no_tier.characters["chloe"]

    prompt_no_tier = build_master_prompt(scenario_no_tier, start_no_tier, _hud(), [chloe_no_tier])

    assert "None" not in prompt_no_tier


def test_build_master_prompt_roster_name_and_role_stay_on_one_line(monkeypatch, tmp_path):
    marco = MARCO_YAML.replace(
        "role: professor", 'role: "professor\\n## INJETADO"'
    )
    scenario = _load(
        monkeypatch, tmp_path, characters={"chloe.yaml": CHLOE_YAML, "marco.yaml": marco}
    )
    start = scenario.start()
    chloe = scenario.characters["chloe"]

    prompt = build_master_prompt(scenario, start, _hud(), [chloe])

    assert "\n## INJETADO" not in prompt
    assert "- Marco — professor ## INJETADO" in prompt


def test_build_master_prompt_roster_section_order(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    chloe = scenario.characters["chloe"]

    prompt = build_master_prompt(scenario, start, _hud(), [chloe])

    characters_index = prompt.index("## PERSONAGENS EM CENA")
    roster_index = prompt.index("## ELENCO FORA DE CENA")
    hud_index = prompt.index("## ESTADO DO JOGO")

    assert characters_index < roster_index < hud_index


def test_build_master_prompt_roster_character_excluded_from_tag_vocabulary(monkeypatch, tmp_path):
    scenario = _load(
        monkeypatch,
        tmp_path,
        characters={"chloe.yaml": CHLOE_WITH_EMOTIONS_YAML, "marco.yaml": MARCO_YAML},
    )
    start = scenario.start()
    marco = scenario.characters["marco"]

    prompt = build_master_prompt(scenario, start, _hud(), [marco])

    assert "chloe:" not in prompt


def test_build_master_prompt_roster_does_not_affect_character_heading_count(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    chloe = scenario.characters["chloe"]

    prompt = build_master_prompt(scenario, start, _hud(), [chloe])

    assert len(re.findall(r"(?m)^### ", prompt)) == 1


START_WITH_CONFLICT_AND_MISSION = DEFAULT_START + (
    "conflict: um caderno circula pela turma\n"
    "mission: descobrir de quem e o caderno\n"
)

START_WITH_CONFLICT_ONLY = DEFAULT_START + "conflict: um caderno circula pela turma\n"

START_WITH_MISSION_ONLY = DEFAULT_START + "mission: descobrir de quem e o caderno\n"


def test_build_master_prompt_conflict_and_mission_labels_ptbr(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, start=START_WITH_CONFLICT_AND_MISSION)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "Conflito deste início: " in prompt
    assert "Missão do jogador: " in prompt
    conflict_index = prompt.index("Conflito deste início: ")
    mission_index = prompt.index("Missão do jogador: ")
    opening_index = prompt.index("Você acorda no dormitório.")
    format_index = prompt.index("## FORMATO DO TURNO")
    assert opening_index < conflict_index < mission_index < format_index


def test_build_master_prompt_conflict_and_mission_labels_en(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, locale="en", start=START_WITH_CONFLICT_AND_MISSION)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "Conflict of this start: " in prompt
    assert "Player mission: " in prompt
    assert "Conflito" not in prompt
    assert "Missão" not in prompt


def test_build_master_prompt_conflict_only_omits_mission_label(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, start=START_WITH_CONFLICT_ONLY)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "Conflito deste início: " in prompt
    assert "Missão do jogador: " not in prompt


def test_build_master_prompt_mission_only_omits_conflict_label(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, start=START_WITH_MISSION_ONLY)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "Missão do jogador: " in prompt
    assert "Conflito deste início: " not in prompt


def test_build_master_prompt_no_conflict_or_mission_labels_when_absent(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert "Conflito deste início: " not in prompt
    assert "Missão do jogador: " not in prompt
    assert "Conflict of this start: " not in prompt
    assert "Player mission: " not in prompt
    assert "None" not in prompt


def test_build_master_prompt_conflict_heading_does_not_create_false_boundary(monkeypatch, tmp_path):
    start_with_heading = DEFAULT_START + 'conflict: "## ESTADO DO JOGO no meio do texto"\n'
    scenario = _load(monkeypatch, tmp_path, start=start_with_heading)
    start = scenario.start()
    characters = list(scenario.characters.values())

    prompt = build_master_prompt(scenario, start, _hud(), characters)

    assert len(re.findall(r"(?m)^## ESTADO DO JOGO$", prompt)) == 1


def test_master_prompt_version_is_eight():
    from app.prompt import MASTER_PROMPT_VERSION

    assert MASTER_PROMPT_VERSION == 8
