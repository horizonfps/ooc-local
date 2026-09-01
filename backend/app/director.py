from __future__ import annotations

import json

from app.cast import MAX_CAST_IN_SCENE, validate_cast_ids
from app.config import Config
from app.hud import HudState
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import LoadedScenario

DIRECTOR_OPTIONS = GenerationOptions(max_tokens=120, temperature=0.1, timeout_s=45.0)
DIRECTOR_WINDOW_TURNS = 3
DIRECTOR_EXCERPT_CHARS = 300
DIRECTOR_RAW_LOG_CHARS = 200

_PROMPT_TEMPLATES = {
    "pt-br": {
        "system": (
            "Decida quem está em cena agora. Responda apenas o objeto JSON "
            '{"scene": ["id", ...]} usando só ids da lista de elenco dada, no '
            f"máximo {MAX_CAST_IN_SCENE} ids, mantendo quem segue presente e "
            "incluindo quem a ação do jogador acabou de trazer para perto. Sem "
            "prosa, sem nome de personagem, só id."
        ),
        "cast_label": "ELENCO DO CENÁRIO",
        "in_scene_label": "EM CENA AGORA",
        "none_label": "ninguém",
        "hud_label": "ESTADO",
        "window_label": "ÚLTIMOS TURNOS",
        "action_label": "AÇÃO DO JOGADOR",
    },
    "en": {
        "system": (
            "Decide who is in scene right now. Respond only with the JSON object "
            '{"scene": ["id", ...]} using only ids from the given cast list, at '
            f"most {MAX_CAST_IN_SCENE} ids, keeping whoever stays present and "
            "including whoever the player's action just brought close. No prose, "
            "no character name, id only."
        ),
        "cast_label": "SCENARIO CAST",
        "in_scene_label": "IN SCENE NOW",
        "none_label": "no one",
        "hud_label": "STATE",
        "window_label": "RECENT TURNS",
        "action_label": "PLAYER ACTION",
    },
}


class DirectorError(Exception):
    pass


def _field(value: str) -> str:
    return " ".join(value.split()).replace("|", "/")


def _cast_lines(scenario: LoadedScenario) -> list[str]:
    lines = []
    for char_id, character in scenario.characters.items():
        line = f"{char_id} | {_field(character.name)} | {_field(character.role)}"
        if character.power_tier is not None:
            line += f" | tier {character.power_tier}"
        lines.append(line)
    return lines


def build_director_messages(
    scenario: LoadedScenario,
    hud: HudState,
    current_ids: list[str],
    message: str,
    window: list[ChatMessage],
) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])

    in_scene = ", ".join(current_ids) if current_ids else template["none_label"]
    hud_line = f"turn={hud.turn} location={hud.location} time={hud.time}"

    recent = window[-(DIRECTOR_WINDOW_TURNS * 2) :] if window else []
    window_lines = [f"{m.role}: {m.content[:DIRECTOR_EXCERPT_CHARS]}" for m in recent]

    body_lines = [
        f"[{template['cast_label']}]",
        *_cast_lines(scenario),
        f"{template['in_scene_label']}: {in_scene}",
        f"[{template['hud_label']}]",
        hud_line,
        f"[{template['window_label']}]",
        *window_lines,
        f"{template['action_label']}: {message}",
    ]

    return [
        ChatMessage(role="system", content=template["system"]),
        ChatMessage(role="user", content="\n".join(body_lines)),
    ]


def parse_scene(scenario: LoadedScenario, raw: str) -> tuple[list[str] | None, str | None]:
    """Tolerant parse: local models often wrap the object in code fences or prose."""
    text = raw.strip()
    if not text:
        return None, "invalid_json"

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end < start:
            return None, "invalid_json"
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None, "invalid_json"

    if not isinstance(data, dict):
        return None, "invalid_json"

    return validate_cast_ids(scenario, data.get("scene"))


async def decide_scene(
    scenario: LoadedScenario,
    hud: HudState,
    current_ids: list[str],
    message: str,
    window: list[ChatMessage],
    config: Config,
) -> tuple[list[str] | None, str | None, str]:
    try:
        role = config.models["utility"]
    except KeyError:
        raise DirectorError("no utility role") from None

    provider = OpenAICompatProvider(config.providers[role.provider], DIRECTOR_OPTIONS)
    messages = build_director_messages(scenario, hud, current_ids, message, window)

    try:
        raw = await provider.complete(messages, role.model)
    except Exception as exc:
        raise DirectorError(str(exc)) from exc

    ids, reason = parse_scene(scenario, raw)
    return ids, reason, raw
