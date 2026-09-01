from __future__ import annotations

import re

from app.hud import HudState
from app.scenario import Character, LoadedScenario, StartConfig

MASTER_PROMPT_VERSION = 3

WEATHER_LABELS: dict[str, dict[str, str]] = {
    "pt-br": {
        "clear": "Limpo",
        "cloudy": "Nublado",
        "rain": "Chuva",
        "storm": "Tempestade",
        "snow": "Neve",
        "fog": "Neblina",
        "night": "Noite",
    },
    "en": {
        "clear": "Clear",
        "cloudy": "Cloudy",
        "rain": "Rain",
        "storm": "Storm",
        "snow": "Snow",
        "fog": "Fog",
        "night": "Night",
    },
}

_HEADING_RE = re.compile(r"^(#{1,6})([ \t].*)$")


def _neutralize_headings(text: str) -> str:
    lines = text.split("\n")
    result = []
    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            level = min(len(match.group(1)) + 3, 6)
            result.append(f"{'#' * level}{match.group(2)}")
        else:
            result.append(line)
    return "\n".join(result)

_TEMPLATES = {
    "pt-br": {
        "narrator_header": "## NARRADOR",
        "narrator_body": (
            "Você é o narrador de uma história interativa. Narre em prosa na "
            "segunda pessoa, sem falar nem decidir pelo jogador."
        ),
        "world_header": "## MUNDO",
        "characters_header": "## PERSONAGENS EM CENA",
        "no_characters": "Nenhum NPC em cena no momento.",
        "role_label": "Papel",
        "personality_label": "Personalidade",
        "voice_label": "Voz",
        "appearance_label": "Aparência",
        "feeling_label": "Sentimento atual",
        "goal_label": "Objetivo",
        "opinion_label": "Opinião sobre o jogador",
        "secret_label": "Segredo (o jogador não sabe)",
        "hud_header": "## ESTADO DO JOGO",
        "hud_turn": "Turno",
        "hud_location": "Local",
        "hud_time": "Hora",
        "hud_weather": "Clima",
        "opening_header": "## CENA DE ABERTURA",
        "summary_header": "## RESUMO DA CAMPANHA",
        "format_header": "## FORMATO DO TURNO",
        "format_body": (
            "Escreva a fala de personagem como `**Nome** | fala`, uma por linha.\n"
            "Mantenha o turno em torno de 350 palavras, nunca passando de 500.\n"
            "Trate o HUD, o relógio e a ficha de status como verdade absoluta: "
            "nunca reescreva HUD, relógio ou ficha de status dentro do texto, "
            "isso é estado do engine.\n"
            "Você pode emitir as tags inline [STAT:nome:±N], "
            "[SPRITE:personagem:emocao] e [BG:local], sempre coladas ao trecho "
            "a que se referem.\n"
            "Nunca escreva bloco de HUD, cabeçalho de turno nem linhas como "
            "\"Local:\", \"Hora:\" ou \"Clima:\" — isso é estado do engine e já "
            "aparece na tela.\n"
            "Nunca repita a ação do jogador como fala: a linha **Você** | ... "
            "é proibida.\n"
            "Responda em português do Brasil."
        ),
    },
    "en": {
        "narrator_header": "## NARRATOR",
        "narrator_body": (
            "You are the narrator of an interactive story. Narrate in prose in "
            "the second person, never speaking or deciding for the player."
        ),
        "world_header": "## WORLD",
        "characters_header": "## CHARACTERS IN SCENE",
        "no_characters": "No NPC is in scene right now.",
        "role_label": "Role",
        "personality_label": "Personality",
        "voice_label": "Voice",
        "appearance_label": "Appearance",
        "feeling_label": "Current feeling",
        "goal_label": "Goal",
        "opinion_label": "Opinion of the player",
        "secret_label": "Secret (the player does not know)",
        "hud_header": "## GAME STATE",
        "hud_turn": "Turn",
        "hud_location": "Location",
        "hud_time": "Time",
        "hud_weather": "Weather",
        "opening_header": "## OPENING SCENE",
        "summary_header": "## CAMPAIGN SUMMARY",
        "format_header": "## TURN FORMAT",
        "format_body": (
            "Write character speech as `**Name** | line`, one per line.\n"
            "Keep the turn around 350 words, never exceeding 500.\n"
            "Treat the HUD, clock and status sheet as absolute truth: never "
            "rewrite HUD, clock or status sheet inside the text, that is "
            "engine state.\n"
            "You may emit the inline tags [STAT:name:±N], "
            "[SPRITE:character:emotion] and [BG:place], always attached to "
            "the passage they refer to.\n"
            "Never write a HUD block, a turn heading or lines like "
            "\"Location:\", \"Time:\" or \"Weather:\" — that is engine state "
            "and is already on screen.\n"
            "Never repeat the player's action as speech: the line "
            "**You** | ... is forbidden.\n"
            "Respond in English."
        ),
    },
}


def _format_character(character: Character, template: dict[str, str]) -> str:
    lines = [
        f"### {character.name}",
        f"{template['role_label']}: {character.role}",
        f"{template['appearance_label']}: {character.appearance}",
        f"{template['personality_label']}: {character.personality}",
        f"{template['voice_label']}: {character.voice}",
        f"{template['feeling_label']}: {character.mind.feeling}",
        f"{template['goal_label']}: {character.mind.goal}",
    ]
    if character.mind.opinion_of_player is not None:
        lines.append(f"{template['opinion_label']}: {character.mind.opinion_of_player}")
    if character.mind.secret_plan is not None:
        lines.append(f"{template['secret_label']}: {character.mind.secret_plan}")
    return "\n".join(lines)


def build_master_prompt(
    scenario: LoadedScenario,
    start: StartConfig,
    hud: HudState,
    characters: list[Character],
    compact: str | None = None,
) -> str:
    template = _TEMPLATES[scenario.meta.locale]
    locale_weather_labels = WEATHER_LABELS[scenario.meta.locale]

    sections = [
        f"{template['narrator_header']}\n{template['narrator_body']}",
        f"{template['world_header']}\n{_neutralize_headings(scenario.world)}",
    ]

    if characters:
        characters_body = "\n\n".join(
            _format_character(character, template) for character in characters
        )
    else:
        characters_body = template["no_characters"]
    sections.append(f"{template['characters_header']}\n{characters_body}")

    weather_label = locale_weather_labels.get(hud.weather, hud.weather)
    hud_body = (
        f"{template['hud_turn']}: {hud.turn}\n"
        f"{template['hud_location']}: {hud.location}\n"
        f"{template['hud_time']}: {hud.time}\n"
        f"{template['hud_weather']}: {weather_label}"
    )
    sections.append(f"{template['hud_header']}\n{hud_body}")

    sections.append(
        f"{template['opening_header']}\n{_neutralize_headings(start.opening_scene)}"
    )

    if compact is not None:
        sections.append(f"{template['summary_header']}\n{compact}")

    sections.append(f"{template['format_header']}\n{template['format_body']}")

    return "\n\n".join(sections)
