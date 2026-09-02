from __future__ import annotations

import json

from pydantic import BaseModel

from app.cast import MindView
from app.config import Config
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import LoadedScenario

MINDS_OPTIONS = GenerationOptions(max_tokens=300, temperature=0.2, timeout_s=45.0)
MIND_FIELD_CHARS = 120
EMOJI_CHARS = 4
MIND_FIELDS = ("attitude", "emoji", "event")
MINDS_NARRATOR_CHARS = 1200
MINDS_RAW_LOG_CHARS = 200
MIND_SHEET_CHARS = 160

_ZWJ = "‍"
_VARIATION_SELECTOR = "️"

_PROMPT_TEMPLATES = {
    "pt-br": {
        "system": (
            "Responda apenas o objeto JSON "
            '{"id": {"attitude": "...", "emoji": "...", "event": "..."}} '
            "usando ids da lista de NPCs em cena, com attitude e event de no "
            f"máximo {MIND_FIELD_CHARS} caracteres cada, emoji com um único "
            "emoji, {} quando nada mudou. Sem prosa, sem nome de personagem no "
            "lugar do id."
        ),
        "cast_label": "NPCS EM CENA",
        "feeling_label": "sentimento",
        "goal_label": "objetivo",
        "current_label": "agora",
        "action_label": "AÇÃO DO JOGADOR",
        "narration_label": "NARRAÇÃO",
    },
    "en": {
        "system": (
            "Respond only with the JSON object "
            '{"id": {"attitude": "...", "emoji": "...", "event": "..."}} '
            "using ids from the NPCs in scene list, with attitude and event at "
            f"most {MIND_FIELD_CHARS} characters each, emoji a single emoji, "
            "{} when nothing changed. No prose, no character name instead of "
            "the id."
        ),
        "cast_label": "NPCS IN SCENE",
        "feeling_label": "feeling",
        "goal_label": "goal",
        "current_label": "now",
        "action_label": "PLAYER ACTION",
        "narration_label": "NARRATION",
    },
}


class MindsError(Exception):
    pass


class MindRejection(BaseModel):
    id: str
    reason: str


def _field(value: str) -> str:
    return " ".join(value.split()).replace("|", "/")


def _clamp_emoji(value: str) -> str:
    chars = list("".join(value.split()))[:EMOJI_CHARS]
    while chars and chars[-1] in (_ZWJ, _VARIATION_SELECTOR):
        chars.pop()
    return "".join(chars)


def build_minds_messages(
    scenario: LoadedScenario,
    cast_ids: list[str],
    previous: dict[str, MindView],
    message: str,
    narrator_text: str,
) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])

    lines = [f"[{template['cast_label']}]"]
    for char_id in cast_ids:
        character = scenario.characters.get(char_id)
        if character is None:
            continue

        sheet = " | ".join(
            [
                _field(character.role),
                _field(character.personality),
                f"{template['feeling_label']}: {_field(character.mind.feeling)}",
                f"{template['goal_label']}: {_field(character.mind.goal)}",
            ]
        )[:MIND_SHEET_CHARS]

        line = f"{char_id} | {_field(character.name)} | {sheet}"
        mind = previous.get(char_id)
        if mind is not None:
            line += f" | {template['current_label']}: {mind.emoji} {mind.attitude}"
        lines.append(line)

    lines.append(f"{template['action_label']}: {message}")
    lines.append(f"[{template['narration_label']}]")
    lines.append(narrator_text[:MINDS_NARRATOR_CHARS])

    return [
        ChatMessage(role="system", content=template["system"]),
        ChatMessage(role="user", content="\n".join(lines)),
    ]


def parse_minds(raw: str) -> tuple[dict | None, str | None]:
    """Tolerant parse: local models often wrap the object in code fences or prose."""
    text = raw.strip()
    if not text:
        return None, "invalid_json"

    data = _loads_tolerant(text)
    if isinstance(data, list):
        data = _list_to_map(data)
    if not isinstance(data, dict):
        return None, "invalid_json"

    return data, None


def _loads_tolerant(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start == -1 or end < start:
            continue
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            continue
    return None


def _list_to_map(items: list) -> dict | None:
    """Accepts the list shape local models drift into: one object per NPC with an id field."""
    out: dict = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            return None
        out[item["id"]] = {key: value for key, value in item.items() if key != "id"}
    return out


def merge_minds(
    previous: dict[str, MindView],
    proposed: dict,
    cast_ids: list[str],
) -> tuple[dict[str, MindView], list[MindRejection]]:
    if not isinstance(proposed, dict):
        return dict(previous), [MindRejection(id="", reason="not_a_map")]

    accepted: dict[str, MindView] = {}
    rejections: list[MindRejection] = []

    for id_, value in proposed.items():
        if id_ not in cast_ids:
            rejections.append(MindRejection(id=id_, reason="not_in_scene"))
            continue
        if not isinstance(value, dict):
            rejections.append(MindRejection(id=id_, reason="invalid_shape"))
            continue

        prev_entry = previous.get(id_)
        fields: dict[str, str] = {}
        for field in MIND_FIELDS:
            candidate = value.get(field)
            if isinstance(candidate, str):
                fields[field] = candidate
            elif prev_entry is not None:
                fields[field] = getattr(prev_entry, field)
            else:
                fields[field] = ""

        attitude = _field(fields["attitude"])[:MIND_FIELD_CHARS]
        event = _field(fields["event"])[:MIND_FIELD_CHARS]
        emoji = _clamp_emoji(fields["emoji"])

        if not attitude and not emoji and not event:
            rejections.append(MindRejection(id=id_, reason="empty"))
            continue

        accepted[id_] = MindView(attitude=attitude, emoji=emoji, event=event)

    return {**previous, **accepted}, rejections


async def think_minds(
    scenario: LoadedScenario,
    cast_ids: list[str],
    previous: dict[str, MindView],
    message: str,
    narrator_text: str,
    config: Config,
) -> tuple[dict | None, str | None, str]:
    try:
        role = config.models["utility"]
    except KeyError:
        raise MindsError("no utility role") from None

    provider = OpenAICompatProvider(config.providers[role.provider], MINDS_OPTIONS)
    messages = build_minds_messages(scenario, cast_ids, previous, message, narrator_text)

    try:
        raw = await provider.complete(messages, role.model)
    except Exception as exc:
        raise MindsError(str(exc)) from exc

    proposed, reason = parse_minds(raw)
    return proposed, reason, raw
