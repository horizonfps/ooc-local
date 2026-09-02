from __future__ import annotations

import re

from app.hud import HudState, stat_views
from app.media import scan_media
from app.scenario import Character, LoadedScenario, StartConfig

MASTER_PROMPT_VERSION = 9

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
        "tier_label": "Tier de poder (1 é o mais forte)",
        "personality_label": "Personalidade",
        "voice_label": "Voz",
        "appearance_label": "Aparência",
        "feeling_label": "Sentimento atual",
        "goal_label": "Objetivo",
        "opinion_label": "Opinião sobre o jogador",
        "secret_label": "Segredo (o jogador não sabe)",
        "roster_header": "## ELENCO FORA DE CENA",
        "roster_intro": (
            "Estes personagens existem no mundo e não estão na cena agora. "
            "Você pode mencioná-los, citar o que fizeram antes ou usá-los em "
            "lembrança, mas não escreva fala nem ação deles no presente: quem "
            "entra em cena é decidido antes do próximo turno, fora da sua "
            "narração."
        ),
        "roster_tier": "tier",
        "hud_header": "## ESTADO DO JOGO",
        "hud_turn": "Turno",
        "hud_location": "Local",
        "hud_time": "Hora",
        "hud_weather": "Clima",
        "status_header": "## STATUS DO JOGADOR",
        "status_level_label": "Nível atual",
        "opening_header": "## CENA DE ABERTURA",
        "conflict_label": "Conflito deste início",
        "mission_label": "Missão do jogador",
        "summary_header": "## RESUMO DA CAMPANHA",
        "tags_header": "## VOCABULÁRIO DE TAGS",
        "tags_intro": (
            "Use somente estas chaves nas tags [SPRITE:...] e [BG:...], "
            "exatamente como estão escritas: são identificadores, não texto "
            "livre. Emita [SPRITE:personagem:emoção] quando a emoção de um "
            "personagem em cena mudar, e [BG:local] quando o local da cena "
            "mudar."
        ),
        "tags_sprites_label": "Emoções por personagem",
        "tags_backgrounds_label": "Backgrounds disponíveis",
        "format_header": "## FORMATO DO TURNO",
        "format_body": (
            "Escreva a fala de personagem como `**Nome** | fala`, uma por linha.\n"
            "Mantenha o turno em torno de 350 palavras, nunca passando de 500.\n"
            "Trate o HUD, o relógio e a ficha de status como verdade absoluta: "
            "nunca reescreva HUD, relógio ou ficha de status dentro do texto, "
            "isso é estado do engine.\n"
            "Você pode emitir as tags inline [STAT:id:±N], "
            "[SPRITE:personagem:emocao], [BG:local] e [LOC:local], sempre "
            "coladas ao trecho a que se referem.\n"
            "Os únicos ids válidos para [STAT:id:±N] são os listados em "
            "## STATUS DO JOGADOR; sem essa seção, não emita essa tag.\n"
            "Quando a cena mudar de lugar, emita [LOC:nome do local] com o "
            "nome do lugar em português, curto, no máximo 60 caracteres. O "
            "HUD só muda de local por essa tag.\n"
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
        "tier_label": "Power tier (1 is the strongest)",
        "personality_label": "Personality",
        "voice_label": "Voice",
        "appearance_label": "Appearance",
        "feeling_label": "Current feeling",
        "goal_label": "Goal",
        "opinion_label": "Opinion of the player",
        "secret_label": "Secret (the player does not know)",
        "roster_header": "## CAST OFF SCENE",
        "roster_intro": (
            "These characters exist in the world and are not in the scene "
            "right now. You may mention them, refer to what they did before "
            "or use them in a memory, but do not write their speech or "
            "action in the present: who enters the scene is decided before "
            "the next turn, outside your narration."
        ),
        "roster_tier": "tier",
        "hud_header": "## GAME STATE",
        "hud_turn": "Turn",
        "hud_location": "Location",
        "hud_time": "Time",
        "hud_weather": "Weather",
        "status_header": "## PLAYER STATUS",
        "status_level_label": "Current level",
        "opening_header": "## OPENING SCENE",
        "conflict_label": "Conflict of this start",
        "mission_label": "Player mission",
        "summary_header": "## CAMPAIGN SUMMARY",
        "tags_header": "## TAG VOCABULARY",
        "tags_intro": (
            "Use only these keys in the [SPRITE:...] and [BG:...] tags, "
            "exactly as written: they are identifiers, not free text. Emit "
            "[SPRITE:character:emotion] when a character's emotion in scene "
            "changes, and [BG:place] when the scene's location changes."
        ),
        "tags_sprites_label": "Emotions per character",
        "tags_backgrounds_label": "Available backgrounds",
        "format_header": "## TURN FORMAT",
        "format_body": (
            "Write character speech as `**Name** | line`, one per line.\n"
            "Keep the turn around 350 words, never exceeding 500.\n"
            "Treat the HUD, clock and status sheet as absolute truth: never "
            "rewrite HUD, clock or status sheet inside the text, that is "
            "engine state.\n"
            "You may emit the inline tags [STAT:id:±N], "
            "[SPRITE:character:emotion], [BG:place] and [LOC:place], always "
            "attached to the passage they refer to.\n"
            "The only valid ids for [STAT:id:±N] are the ones listed in "
            "## PLAYER STATUS; without that section, do not emit that tag.\n"
            "When the scene moves to another place, emit [LOC:place name] "
            "with a short name, at most 60 characters. The HUD only changes "
            "location through this tag.\n"
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
    ]
    if character.power_tier is not None:
        lines.append(f"{template['tier_label']}: {character.power_tier}")
    lines += [
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


def _roster(
    scenario: LoadedScenario, characters: list[Character], template: dict[str, str]
) -> str | None:
    """One-line-per-character summary of the cast that is not in scene."""
    off_scene = [
        candidate
        for candidate in scenario.characters.values()
        if not any(candidate is character for character in characters)
    ]
    if not off_scene:
        return None

    lines = [template["roster_intro"]]
    for character in off_scene:
        name = " ".join(character.name.split())
        role = " ".join(character.role.split())
        line = f"- {name} — {role}"
        if character.power_tier is not None:
            line += f" ({template['roster_tier']} {character.power_tier})"
        lines.append(line)
    return "\n".join(lines)


def _character_id(scenario: LoadedScenario, character: Character) -> str | None:
    for char_id, candidate in scenario.characters.items():
        if candidate is character:
            return char_id
    return None


def _tag_vocabulary(
    scenario: LoadedScenario, characters: list[Character], template: dict[str, str]
) -> str | None:
    """Deterministic list of the only valid [SPRITE:...]/[BG:...] keys for this turn."""
    sprite_lines = []
    for character in characters:
        if len(character.emotions) <= 1:
            continue
        char_id = _character_id(scenario, character)
        if char_id is None:
            continue
        sprite_lines.append(f"{char_id}: {', '.join(character.emotions)}")

    backgrounds = sorted(scan_media(scenario.id).backgrounds)

    if not sprite_lines and not backgrounds:
        return None

    parts = [template["tags_intro"]]
    if sprite_lines:
        parts.append(f"{template['tags_sprites_label']}:\n" + "\n".join(sprite_lines))
    if backgrounds:
        parts.append(f"{template['tags_backgrounds_label']}: {', '.join(backgrounds)}")
    return "\n".join(parts)


def _status(scenario: LoadedScenario, hud: HudState, template: dict[str, str]) -> str | None:
    """One line per stat, in scenario order; the same projection the UI uses. Description
    comes from the scenario's StatDef, which stat_views does not carry to the UI."""
    views = stat_views(scenario, hud)
    if not views:
        return None

    descriptions = {stat.id: stat.description for stat in scenario.stats}
    lines = []
    for view in views:
        line = f"{view.name}: {view.value}/{view.max}"
        description = descriptions.get(view.id)
        if description:
            line += f" — {' '.join(description.split())}"
        if view.level is not None:
            line += f" {template['status_level_label']}: {' '.join(view.level.split())}"
        lines.append(line)
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

    roster = _roster(scenario, characters, template)
    if roster is not None:
        sections.append(f"{template['roster_header']}\n{roster}")

    weather_label = locale_weather_labels.get(hud.weather, hud.weather)
    hud_body = (
        f"{template['hud_turn']}: {hud.turn}\n"
        f"{template['hud_location']}: {hud.location}\n"
        f"{template['hud_time']}: {hud.time}\n"
        f"{template['hud_weather']}: {weather_label}"
    )
    sections.append(f"{template['hud_header']}\n{hud_body}")

    status = _status(scenario, hud, template)
    if status is not None:
        sections.append(f"{template['status_header']}\n{status}")

    opening_parts = [_neutralize_headings(start.opening_scene).strip()]
    if start.conflict is not None:
        opening_parts.append(
            f"{template['conflict_label']}: {_neutralize_headings(start.conflict).strip()}"
        )
    if start.mission is not None:
        opening_parts.append(
            f"{template['mission_label']}: {_neutralize_headings(start.mission).strip()}"
        )
    sections.append(f"{template['opening_header']}\n" + "\n\n".join(opening_parts))

    if compact is not None:
        sections.append(f"{template['summary_header']}\n{compact}")

    tag_vocabulary = _tag_vocabulary(scenario, characters, template)
    if tag_vocabulary is not None:
        sections.append(f"{template['tags_header']}\n{tag_vocabulary}")

    sections.append(f"{template['format_header']}\n{template['format_body']}")

    return "\n\n".join(sections)
