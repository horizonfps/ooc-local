from __future__ import annotations

import pytest

from app.commands import (
    COMMAND_ARG_CHARS,
    DEFAULT_GLOBAL_COMMANDS,
    GLOBAL_COMMANDS_PATH,
    META_PROMPT_TEMPLATES,
    GlobalCommandDef,
    ResolvedCommand,
    UnknownCommand,
    build_meta_user_message,
    command_views,
    global_commands_path,
    load_global_commands,
    resolve_command,
)
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

COMMANDS_YAML = """\
- name: fofoca
  description: espalha uma fofoca
  prompt: espalhe uma fofoca sobre o personagem atual
- name: inventario
  description: mostra o inventario
  prompt: liste o inventario do jogador
"""


def _write_scenario(root, scenario_id, *, locale="pt-br", commands=COMMANDS_YAML):
    scenario_yaml = SCENARIO_YAML_PTBR if locale == "pt-br" else SCENARIO_YAML_EN

    scenario_path = root / scenario_id
    scenario_path.mkdir(parents=True)
    (scenario_path / "scenario.yaml").write_text(scenario_yaml, encoding="utf-8")
    (scenario_path / "world.md").write_text(WORLD_MD, encoding="utf-8")

    starts_dir = scenario_path / "starts"
    starts_dir.mkdir()
    (starts_dir / "default.yaml").write_text(DEFAULT_START, encoding="utf-8")

    characters_dir = scenario_path / "characters"
    characters_dir.mkdir()
    (characters_dir / "chloe.yaml").write_text(CHLOE_YAML, encoding="utf-8")

    if commands is not None:
        (scenario_path / "commands.yaml").write_text(commands, encoding="utf-8")

    return scenario_path


def _load(monkeypatch, tmp_path, *, scenario_id="exemplo-escola", locale="pt-br", commands=COMMANDS_YAML):
    _write_scenario(tmp_path, scenario_id, locale=locale, commands=commands)
    monkeypatch.setattr("app.scenario.scenarios_dir", lambda: tmp_path)
    return load_scenario(scenario_id)


def _globals():
    return [
        GlobalCommandDef(
            name="diary",
            description={"pt-br": "diario", "en": "diary"},
            prompt={"pt-br": "escreva o diario", "en": "write the diary"},
        ),
    ]


# --- load_global_commands ---


def test_missing_file_creates_defaults_and_returns_three_commands(tmp_path):
    path = tmp_path / "commands.yaml"

    commands = load_global_commands(path)

    assert path.read_text(encoding="utf-8") == DEFAULT_GLOBAL_COMMANDS
    assert [c.name for c in commands] == ["diary", "inner", "recap"]
    for command in commands:
        assert set(command.description) == {"pt-br", "en"}
        assert set(command.prompt) == {"pt-br", "en"}


def test_existing_file_is_not_overwritten(tmp_path):
    path = tmp_path / "commands.yaml"
    custom = "- name: only\n  description: {pt-br: so}\n  prompt: {pt-br: faca so}\n"
    path.write_text(custom, encoding="utf-8")

    commands = load_global_commands(path)

    assert [c.name for c in commands] == ["only"]
    assert path.read_text(encoding="utf-8") == custom


def test_global_commands_path_uses_env_var(monkeypatch, tmp_path):
    target = tmp_path / "g.yaml"
    monkeypatch.setenv("OOC_COMMANDS_FILE", str(target))

    assert global_commands_path() == target

    commands = load_global_commands()

    assert target.exists()
    assert [c.name for c in commands] == ["diary", "inner", "recap"]


def test_global_commands_path_defaults_without_env(monkeypatch):
    monkeypatch.delenv("OOC_COMMANDS_FILE", raising=False)

    assert global_commands_path() == GLOBAL_COMMANDS_PATH


def test_empty_file_returns_empty_list_without_emit(tmp_path, monkeypatch):
    path = tmp_path / "commands.yaml"
    path.write_text("", encoding="utf-8")
    events = []
    monkeypatch.setattr("app.commands.emit", lambda event, **props: events.append((event, props)))

    commands = load_global_commands(path)

    assert commands == []
    assert events == []


@pytest.mark.parametrize(
    "content",
    [
        "- name: [\n",  # malformed yaml
        "diary: {}\n",  # root is a mapping, not a list
        "- name: diary\n  extra: x\n",  # extra field forbidden
        (
            "- name: dup\n"
            "  description: {pt-br: a}\n"
            "  prompt: {pt-br: a}\n"
            "- name: dup\n"
            "  description: {pt-br: b}\n"
            "  prompt: {pt-br: b}\n"
        ),  # duplicate name
        '- name: "Diary!"\n  description: {pt-br: a}\n  prompt: {pt-br: a}\n',  # invalid name
        (
            "- name: ok\n"
            "  description: {pt-br: certo}\n"
            "  prompt: {pt-br: faca certo}\n"
            '- name: "Bad!"\n'
            "  description: {pt-br: errado}\n"
            "  prompt: {pt-br: faca errado}\n"
        ),  # one invalid item rejects the whole file
    ],
)
def test_invalid_file_falls_back_to_defaults_and_emits(tmp_path, monkeypatch, content):
    path = tmp_path / "commands.yaml"
    path.write_text(content, encoding="utf-8")
    events = []
    monkeypatch.setattr("app.commands.emit", lambda event, **props: events.append((event, props)))

    commands = load_global_commands(path)

    assert [c.name for c in commands] == ["diary", "inner", "recap"]
    assert events and events[0][0] == "commands_file_invalid"
    assert events[0][1]["path"] == str(path)
    assert len(events[0][1]["error"]) <= 300
    assert path.read_text(encoding="utf-8") == content


# --- resolve_command ---


def test_resolve_scenario_command(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    resolved = resolve_command("!fofoca", scenario, [])

    assert resolved == ResolvedCommand(
        name="fofoca",
        scope="scenario",
        prompt="espalhe uma fofoca sobre o personagem atual",
        arg=None,
    )


def test_resolve_global_command_picks_scenario_locale(monkeypatch, tmp_path):
    scenario_ptbr = _load(monkeypatch, tmp_path, scenario_id="exemplo-ptbr", locale="pt-br")
    resolved_ptbr = resolve_command("/diary", scenario_ptbr, _globals())
    assert resolved_ptbr.scope == "global"
    assert resolved_ptbr.prompt == "escreva o diario"

    scenario_en = _load(monkeypatch, tmp_path, scenario_id="exemplo-en", locale="en")
    resolved_en = resolve_command("/diary", scenario_en, _globals())
    assert resolved_en.prompt == "write the diary"


def test_resolve_scenario_command_with_arg(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    resolved = resolve_command("!fofoca sobre a Chloe", scenario, [])

    assert resolved.arg == "sobre a Chloe"


def test_resolve_command_clamps_arg(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    resolved = resolve_command("!fofoca " + "x" * 500, scenario, [])

    assert len(resolved.arg) == COMMAND_ARG_CHARS


def test_resolve_command_sigil_followed_by_space_is_unknown(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    with pytest.raises(UnknownCommand) as excinfo:
        resolve_command("! fofoca", scenario, [])

    assert excinfo.value.name == ""


def test_non_utf8_file_falls_back_to_defaults_and_emits(tmp_path, monkeypatch):
    path = tmp_path / "commands.yaml"
    path.write_bytes(b"\xff\xfe- name: diary\n")
    events = []
    monkeypatch.setattr("app.commands.emit", lambda event, **props: events.append((event, props)))

    commands = load_global_commands(path)

    assert [c.name for c in commands] == ["diary", "inner", "recap"]
    assert events and events[0][0] == "commands_file_invalid"


def test_resolve_command_trims_surrounding_whitespace(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    resolved = resolve_command("  !fofoca  ", scenario, [])

    assert resolved.name == "fofoca"
    assert resolved.arg is None


def test_resolve_command_splits_on_newline(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    resolved = resolve_command("!fofoca\nlinha 2", scenario, [])

    assert resolved.arg == "linha 2"


def test_resolve_command_casefolds_name(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)

    resolved = resolve_command("!FOFOCA", scenario, [])

    assert resolved.name == "fofoca"


@pytest.mark.parametrize("text", ["texto normal", "", "   ", "vou ver /diary"])
def test_resolve_command_returns_none_for_non_commands(monkeypatch, tmp_path, text):
    scenario = _load(monkeypatch, tmp_path)

    assert resolve_command(text, scenario, []) is None


@pytest.mark.parametrize(
    "text,expected_prefix,expected_name",
    [
        ("!Fofoca!", "!", "fofoca!"),  # name has invalid characters
        ("!", "!", ""),  # empty name after !
        ("/ ", "/", ""),  # empty name after /
        ("!diary", "!", "diary"),  # name only exists in globals, no cross-scope fallback
        ("/fofoca", "/", "fofoca"),  # name only exists in scenario, no cross-scope fallback
    ],
)
def test_resolve_command_raises_unknown_command(monkeypatch, tmp_path, text, expected_prefix, expected_name):
    scenario = _load(monkeypatch, tmp_path)

    with pytest.raises(UnknownCommand) as exc_info:
        resolve_command(text, scenario, _globals())

    assert exc_info.value.prefix == expected_prefix
    assert exc_info.value.name == expected_name


def test_resolve_command_scenario_without_commands_always_unknown(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, scenario_id="sem-comandos", commands=None)
    assert scenario.commands == []

    with pytest.raises(UnknownCommand):
        resolve_command("!fofoca", scenario, [])


def test_resolve_command_global_prompt_falls_back_to_only_locale(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    globals_ = [
        GlobalCommandDef(
            name="diary",
            description={"de": "Tagebuch"},
            prompt={"de": "schreib das tagebuch"},
        )
    ]

    resolved = resolve_command("/diary", scenario, globals_)

    assert resolved.prompt == "schreib das tagebuch"


# --- build_meta_user_message ---


def test_build_meta_user_message_order():
    resolved = ResolvedCommand(name="diary", scope="global", prompt="escreva o diario", arg=None)

    message = build_meta_user_message(resolved, "pt-br")

    envelope = META_PROMPT_TEMPLATES["pt-br"]["envelope"]
    assert message.index(envelope) < message.index("escreva o diario")


def test_build_meta_user_message_arg_label():
    resolved = ResolvedCommand(name="fofoca", scope="scenario", prompt="espalhe", arg="sobre a Chloe")
    message = build_meta_user_message(resolved, "pt-br")
    assert message.endswith("Complemento do jogador: sobre a Chloe")

    resolved_no_arg = ResolvedCommand(name="fofoca", scope="scenario", prompt="espalhe", arg=None)
    message_no_arg = build_meta_user_message(resolved_no_arg, "pt-br")
    assert "Complemento do jogador" not in message_no_arg


def test_build_meta_user_message_locale():
    resolved = ResolvedCommand(name="diary", scope="global", prompt="write it", arg=None)

    message_en = build_meta_user_message(resolved, "en")
    for word in ("Responda", "narrativa", "jogador"):
        assert word not in message_en

    message_unknown = build_meta_user_message(resolved, "de")
    assert message_unknown.startswith(META_PROMPT_TEMPLATES["pt-br"]["envelope"])


# --- command_views ---


def test_command_views_scenario_before_global(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    globals_ = [
        GlobalCommandDef(name="diary", description={"pt-br": "diario"}, prompt={"pt-br": "x"}),
        GlobalCommandDef(name="inner", description={"pt-br": "interior"}, prompt={"pt-br": "y"}),
        GlobalCommandDef(name="recap", description={"pt-br": "recapitular"}, prompt={"pt-br": "z"}),
    ]

    views = command_views(scenario, globals_, "pt-br")

    assert len(views) == 5
    assert [v.scope for v in views] == ["scenario", "scenario", "global", "global", "global"]
    assert views[0].name == "fofoca"
    assert views[2].name == "diary"


def test_command_views_global_description_locale_fallback(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path)
    globals_ = [GlobalCommandDef(name="diary", description={"de": "Tagebuch"}, prompt={"de": "x"})]

    views = command_views(scenario, globals_, "pt-br")

    assert views[-1].description == "Tagebuch"


def test_command_views_empty(monkeypatch, tmp_path):
    scenario = _load(monkeypatch, tmp_path, scenario_id="vazio", commands=None)

    views = command_views(scenario, [], "pt-br")

    assert views == []
