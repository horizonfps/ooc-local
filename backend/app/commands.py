from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.config import CONFIG_DIR
from app.observability import emit
from app.scenario import CommandView, LoadedScenario

GLOBAL_COMMANDS_PATH = CONFIG_DIR / "commands.yaml"
GLOBAL_COMMANDS_ENV = "OOC_COMMANDS_FILE"
SCENARIO_SIGIL = "!"
GLOBAL_SIGIL = "/"
COMMAND_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
COMMAND_ARG_CHARS = 200

DEFAULT_GLOBAL_COMMANDS = """\
- name: diary
  description:
    pt-br: Diário do jogador sobre o dia
    en: Player diary of the day
  prompt:
    pt-br: >
      Escreva a entrada de diário que o jogador escreveria sobre o que
      aconteceu até aqui: primeira pessoa, no máximo 200 palavras, só o que
      ele viu, sentiu e decidiu.
    en: >
      Write the diary entry the player would write about what happened so
      far: first person, at most 200 words, only what they saw, felt and
      decided.
- name: inner
  description:
    pt-br: Pensamentos de cada NPC em cena
    en: Thoughts of each NPC in scene
  prompt:
    pt-br: >
      Liste, uma linha por NPC em cena, o que ele pensa agora sobre o jogador
      e sobre a situação, no formato "Nome: pensamento". Sem diálogo e sem
      ação.
    en: >
      List, one line per NPC in scene, what they think right now about the
      player and the situation, in the format "Name: thought". No dialogue,
      no action.
- name: recap
  description:
    pt-br: Recapitulação da história até aqui
    en: Recap of the story so far
  prompt:
    pt-br: >
      Recapitule a história até aqui em no máximo 150 palavras: o que o
      jogador fez, o que ficou pendente e quem quer o quê. Não invente fato
      novo.
    en: >
      Recap the story so far in at most 150 words: what the player did, what
      is pending and who wants what. Do not invent new facts.
"""

META_PROMPT_TEMPLATES = {
    "pt-br": {
        "envelope": (
            "Responda fora da narrativa, sem avançar a história, sem tag e "
            "sem fala de personagem em cena. Este pedido não é uma ação do "
            "jogador."
        ),
        "arg_label": "Complemento do jogador",
    },
    "en": {
        "envelope": (
            "Answer outside the narrative, without advancing the story, "
            "without tags and without in-scene character speech. This "
            "request is not a player action."
        ),
        "arg_label": "Player note",
    },
}


class GlobalCommandDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: dict[str, str]
    prompt: dict[str, str]

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not COMMAND_NAME_RE.match(value):
            raise ValueError(f"invalid command name '{value}', expected [a-z0-9_-]+")
        return value

    @field_validator("description", "prompt")
    @classmethod
    def _validate_not_empty(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("must not be empty")
        return value


class ResolvedCommand(BaseModel):
    name: str
    scope: Literal["scenario", "global"]
    prompt: str
    arg: str | None = None


class UnknownCommand(Exception):
    def __init__(self, prefix: str, name: str) -> None:
        self.prefix = prefix
        self.name = name
        super().__init__(f"unknown command '{prefix}{name}'")


def _clip(message: str) -> str:
    message = message.replace("\n", " ")
    return message[:300]


def _summarize(exc: ValidationError) -> str:
    parts = [f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}" for error in exc.errors()]
    summary = f"{len(parts)} erro(s): " + "; ".join(parts)
    return _clip(summary)


def _default_commands() -> list[GlobalCommandDef]:
    data = yaml.safe_load(DEFAULT_GLOBAL_COMMANDS)
    return [GlobalCommandDef.model_validate(item) for item in data]


def global_commands_path() -> Path:
    env_path = os.environ.get(GLOBAL_COMMANDS_ENV)
    if env_path:
        return Path(env_path)
    return GLOBAL_COMMANDS_PATH


def load_global_commands(path: Path | None = None) -> list[GlobalCommandDef]:
    resolved = path if path is not None else global_commands_path()
    if not resolved.exists():
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(DEFAULT_GLOBAL_COMMANDS, encoding="utf-8")

    try:
        raw = resolved.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        emit("commands_file_invalid", path=str(resolved), error=_clip(str(exc)))
        return _default_commands()

    if data is None:
        return []

    if not isinstance(data, list):
        emit(
            "commands_file_invalid",
            path=str(resolved),
            error=_clip(f"root must be a list, got {type(data).__name__}"),
        )
        return _default_commands()

    try:
        commands = [GlobalCommandDef.model_validate(item) for item in data]
    except ValidationError as exc:
        emit("commands_file_invalid", path=str(resolved), error=_summarize(exc))
        return _default_commands()

    seen: set[str] = set()
    for command in commands:
        if command.name in seen:
            emit(
                "commands_file_invalid",
                path=str(resolved),
                error=_clip(f"duplicate command name '{command.name}'"),
            )
            return _default_commands()
        seen.add(command.name)

    return commands


def _pick_locale(mapping: dict[str, str], locale: str) -> str:
    if locale in mapping:
        return mapping[locale]
    if not mapping:
        return ""
    return mapping[sorted(mapping)[0]]


def resolve_command(
    text: str,
    scenario: LoadedScenario,
    global_commands: list[GlobalCommandDef],
) -> ResolvedCommand | None:
    stripped = text.strip()
    if not stripped or stripped[0] not in (SCENARIO_SIGIL, GLOBAL_SIGIL):
        return None

    prefix = stripped[0]
    head = stripped[1:]
    # The name runs up to the first whitespace; a sigil followed by a space names nothing.
    match = re.match(r"(\S*)(?:\s+(.*))?$", head, re.DOTALL)
    name_part = match.group(1) if match else ""
    rest = (match.group(2) or "") if match else ""

    name = name_part.casefold()
    arg = rest.strip()[:COMMAND_ARG_CHARS] or None

    if not name or not COMMAND_NAME_RE.match(name):
        raise UnknownCommand(prefix, name)

    if prefix == SCENARIO_SIGIL:
        scope: Literal["scenario", "global"] = "scenario"
        found = next((c for c in scenario.commands if c.name == name), None)
        if found is None:
            raise UnknownCommand(prefix, name)
        prompt = found.prompt
    else:
        scope = "global"
        found_global = next((c for c in global_commands if c.name == name), None)
        if found_global is None:
            raise UnknownCommand(prefix, name)
        prompt = _pick_locale(found_global.prompt, scenario.meta.locale)

    return ResolvedCommand(name=name, scope=scope, prompt=prompt, arg=arg)


def build_meta_user_message(resolved: ResolvedCommand, locale: str) -> str:
    template = META_PROMPT_TEMPLATES.get(locale, META_PROMPT_TEMPLATES["pt-br"])
    message = f"{template['envelope']}\n\n{resolved.prompt}"
    if resolved.arg:
        message += f"\n\n{template['arg_label']}: {resolved.arg}"
    return message


def command_views(
    scenario: LoadedScenario,
    global_commands: list[GlobalCommandDef],
    locale: str,
) -> list[CommandView]:
    views = [
        CommandView(name=c.name, description=c.description, scope="scenario") for c in scenario.commands
    ]
    views += [
        CommandView(name=c.name, description=_pick_locale(c.description, locale), scope="global")
        for c in global_commands
    ]
    return views
