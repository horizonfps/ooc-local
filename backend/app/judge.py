from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel

from app.config import Config
from app.hud import DynamicStat, HudState
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import LoadedScenario, StatDef

JUDGE_OPTIONS = GenerationOptions(max_tokens=200, temperature=0.1, timeout_s=45.0)
JUDGE_NARRATOR_CHARS = 1200
JUDGE_RAW_LOG_CHARS = 200
DYNAMIC_STAT_NAME_CHARS = 40
STAT_ID_RE = re.compile(r"^[a-z0-9_-]+$")

_PROMPT_TEMPLATES = {
    "pt-br": {
        "system": (
            "Avalie o turno e proponha ajustes de atributos. Responda apenas o "
            'objeto JSON {"stats": {"id": N}}, usando só ids da lista dada, N '
            "inteiro: positivo quando a narração beneficia o jogador nesse "
            'atributo, negativo quando prejudica. Quando a linha do atributo '
            'trouxer "max ±N", o ajuste daquele atributo não pode passar de N '
            "para mais nem para menos. Omita ids sem consequência clara na "
            "narração; {} quando nada mudou. Sem prosa."
        ),
        "system_dynamic": (
            ' Também pode propor atributos novos em "new": '
            '[{"id": "...", "name": "...", "value": N, "max": N, "kind": "stat"}]. '
            'Use kind "item" para o que o jogador carrega, "skill" para o que '
            'ele sabe fazer, "stat" para o resto.'
        ),
        "stats_label": "ATRIBUTOS",
        "touched_label": "(já ajustado neste turno)",
        "action_label": "AÇÃO DO JOGADOR",
        "narration_label": "NARRAÇÃO",
    },
    "en": {
        "system": (
            "Judge the turn and propose stat adjustments. Respond only with the "
            'JSON object {"stats": {"id": N}}, using only ids from the given '
            "list, N an integer: positive when the narration benefits the "
            "player on that stat, negative when it hurts. When the stat line "
            'carries "max ±N", that stat\'s adjustment cannot exceed N in '
            "either direction. Omit ids with no clear consequence in the "
            "narration; {} when nothing changed. No prose."
        ),
        "system_dynamic": (
            ' You may also propose new stats in "new": '
            '[{"id": "...", "name": "...", "value": N, "max": N, "kind": "stat"}]. '
            'Use kind "item" for what the player carries, "skill" for what '
            'they know how to do, "stat" for everything else.'
        ),
        "stats_label": "STATS",
        "touched_label": "(already adjusted this turn)",
        "action_label": "PLAYER ACTION",
        "narration_label": "NARRATION",
    },
}


class JudgeError(Exception):
    pass


class StatChange(BaseModel):
    id: str
    delta: int
    value: int
    source: Literal["tag", "judge"]


class StatRejection(BaseModel):
    id: str
    reason: str


def _field(value: str) -> str:
    return " ".join(value.split()).replace("|", "/")


def _stat_lines(
    scenario: LoadedScenario, hud: HudState, touched_ids: list[str], touched_label: str
) -> list[str]:
    lines = []
    for stat in scenario.stats:
        value = hud.stats.get(stat.id, stat.default)
        line = f"{stat.id} | {_field(stat.name)} | {value}/{stat.min}..{stat.max}"
        if stat.description is not None:
            line += f" | {_field(stat.description)}"
        if stat.max_delta is not None:
            line += f" | max ±{stat.max_delta}"
        if stat.id in touched_ids:
            line += f" {touched_label}"
        lines.append(line)
    for stat_id, dynamic in hud.dynamic_stats.items():
        line = f"{stat_id} | {_field(dynamic.name)} | {dynamic.value}/{dynamic.min}..{dynamic.max}"
        if stat_id in touched_ids:
            line += f" {touched_label}"
        lines.append(line)
    return lines


def build_judge_messages(
    scenario: LoadedScenario,
    hud: HudState,
    message: str,
    narrator_text: str,
    touched_ids: list[str],
) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])

    system = template["system"]
    if scenario.meta.allow_dynamic_stats:
        system += template["system_dynamic"]

    stat_lines = _stat_lines(scenario, hud, touched_ids, template["touched_label"])

    body_lines = [
        f"[{template['stats_label']}]",
        *stat_lines,
        f"{template['action_label']}: {message}",
        f"[{template['narration_label']}]",
        narrator_text[:JUDGE_NARRATOR_CHARS],
    ]

    return [
        ChatMessage(role="system", content=system),
        ChatMessage(role="user", content="\n".join(body_lines)),
    ]


_EXPLICIT_PLUS = re.compile(r"(:\s*)\+(?=\d)")


def parse_judgement(raw: str) -> tuple[dict | None, str | None]:
    """Tolerant parse: local models often wrap the object in code fences or prose."""
    text = _EXPLICIT_PLUS.sub(r"\1", raw.strip())
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

    return data, None


def _judgeable_stats(
    scenario: LoadedScenario, hud: HudState
) -> dict[str, tuple[int, int, int, int | None]]:
    """id -> (current value, min, max, max_delta) for every id the judge may touch."""
    judgeable: dict[str, tuple[int, int, int, int | None]] = {}
    for stat in scenario.stats:
        value = hud.stats.get(stat.id, stat.default)
        judgeable[stat.id] = (value, stat.min, stat.max, stat.max_delta)
    for stat_id, dynamic in hud.dynamic_stats.items():
        judgeable[stat_id] = (dynamic.value, dynamic.min, dynamic.max, None)
    return judgeable


def _apply_one(
    current: int, delta: int, minimum: int, maximum: int, max_delta: int | None
) -> tuple[int, int]:
    """Clamp delta to the stat's max_delta when declared, then clamp the value to [min, max].
    Returns (new_value, effective_delta)."""
    if max_delta is not None:
        delta = max(-max_delta, min(max_delta, delta))
    new_value = max(minimum, min(maximum, current + delta))
    return new_value, new_value - current


def apply_judgement(
    scenario: LoadedScenario,
    hud: HudState,
    judgement: dict,
    touched_ids: list[str],
) -> tuple[HudState, list[StatChange], list[StatRejection]]:
    judgeable = _judgeable_stats(scenario, hud)
    new_stats = dict(hud.stats)
    new_dynamic = dict(hud.dynamic_stats)
    changes: list[StatChange] = []
    rejections: list[StatRejection] = []

    stats_field = judgement.get("stats")
    if stats_field is not None and not isinstance(stats_field, dict):
        rejections.append(StatRejection(id="stats", reason="not_a_map"))
    elif isinstance(stats_field, dict):
        for stat_id, delta in stats_field.items():
            if stat_id not in judgeable:
                rejections.append(StatRejection(id=stat_id, reason="unknown_id"))
                continue
            if stat_id in touched_ids:
                rejections.append(StatRejection(id=stat_id, reason="touched_by_tag"))
                continue
            if type(delta) is not int:
                rejections.append(StatRejection(id=stat_id, reason="not_an_int"))
                continue
            current, minimum, maximum, max_delta = judgeable[stat_id]
            new_value, effective_delta = _apply_one(current, delta, minimum, maximum, max_delta)
            if new_value == current:
                rejections.append(StatRejection(id=stat_id, reason="no_change"))
                continue
            if stat_id in new_dynamic:
                new_dynamic[stat_id] = new_dynamic[stat_id].model_copy(update={"value": new_value})
            else:
                new_stats[stat_id] = new_value
            judgeable[stat_id] = (new_value, minimum, maximum, max_delta)
            changes.append(
                StatChange(id=stat_id, delta=effective_delta, value=new_value, source="judge")
            )

    new_field = judgement.get("new")
    if not scenario.meta.allow_dynamic_stats:
        if new_field:
            rejections.append(StatRejection(id="new", reason="dynamic_disabled"))
    elif new_field is not None:
        if not isinstance(new_field, list):
            rejections.append(StatRejection(id="new", reason="not_a_list"))
        else:
            created_ids: set[str] = set()
            over_cap = False
            cap = scenario.meta.max_dynamic_stats
            for item in new_field:
                item_id = item.get("id") if isinstance(item, dict) else None
                rejection_id = item_id if isinstance(item_id, str) else ""

                if over_cap:
                    rejections.append(StatRejection(id=rejection_id, reason="over_cap"))
                    continue

                if not isinstance(item, dict):
                    rejections.append(StatRejection(id=rejection_id, reason="invalid_shape"))
                    continue

                min_value = item.get("min", 0)
                name = item.get("name")
                value = item.get("value")
                max_value = item.get("max")

                if (
                    not isinstance(item_id, str)
                    or not isinstance(name, str)
                    or type(value) is not int
                    or type(max_value) is not int
                    or type(min_value) is not int
                ):
                    rejections.append(StatRejection(id=rejection_id, reason="invalid_shape"))
                    continue
                if max_value <= min_value:
                    rejections.append(StatRejection(id=rejection_id, reason="invalid_shape"))
                    continue

                if not STAT_ID_RE.match(item_id):
                    rejections.append(StatRejection(id=item_id, reason="invalid_id"))
                    continue

                if item_id in judgeable or item_id in created_ids:
                    rejections.append(StatRejection(id=item_id, reason="duplicate_id"))
                    continue

                if cap is not None and len(hud.dynamic_stats) + len(created_ids) >= cap:
                    rejections.append(StatRejection(id=item_id, reason="over_cap"))
                    over_cap = True
                    continue

                kind = item.get("kind", "stat")
                if kind not in ("stat", "item", "skill"):
                    rejections.append(StatRejection(id=item_id, reason="invalid_kind"))
                    continue

                created_ids.add(item_id)
                clamped_value = max(min_value, min(max_value, value))
                new_dynamic[item_id] = DynamicStat(
                    name=_field(name)[:DYNAMIC_STAT_NAME_CHARS],
                    value=clamped_value,
                    min=min_value,
                    max=max_value,
                    kind=kind,
                )
                changes.append(
                    StatChange(id=item_id, delta=0, value=clamped_value, source="judge")
                )

    if not changes:
        return hud, [], rejections

    for stat in scenario.stats:
        new_stats.setdefault(stat.id, hud.stats.get(stat.id, stat.default))

    new_hud = hud.model_copy(update={"stats": new_stats, "dynamic_stats": new_dynamic})
    return new_hud, changes, rejections


async def judge_turn(
    scenario: LoadedScenario,
    hud: HudState,
    message: str,
    narrator_text: str,
    touched_ids: list[str],
    config: Config,
) -> tuple[dict | None, str | None, str]:
    try:
        role = config.models["utility"]
    except KeyError:
        raise JudgeError("no utility role") from None

    provider = OpenAICompatProvider(config.providers[role.provider], JUDGE_OPTIONS)
    messages = build_judge_messages(scenario, hud, message, narrator_text, touched_ids)

    try:
        raw = await provider.complete(messages, role.model)
    except Exception as exc:
        raise JudgeError(str(exc)) from exc

    judgement, reason = parse_judgement(raw)
    return judgement, reason, raw
