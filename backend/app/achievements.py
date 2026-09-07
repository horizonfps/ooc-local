from __future__ import annotations

import json
from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from app.config import Config
from app.hud import HudState
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import AchievementDef, LoadedScenario

ACHIEVEMENT_CHECK_EVERY = 3
ACHIEVEMENT_WINDOW_TURNS = 4
ACHIEVEMENT_EXCERPT_CHARS = 400
ACHIEVEMENT_RAW_LOG_CHARS = 200
MAX_CANDIDATES_PER_CALL = 8

_PROMPT_TEMPLATES = {
    "pt-br": {
        "system": (
            "Julgue cada condição contra o que aconteceu. Responda apenas o "
            'objeto JSON {"verdicts": [{"id": "...", "met": true|false}]}, '
            "usando só ids da lista de candidatos dada. Marque met: true "
            "somente quando a condição está satisfeita de fato no histórico "
            "apresentado, nunca por intenção ou por probabilidade. Sem prosa."
        ),
        "candidates_label": "CANDIDATOS",
        "window_label": "ÚLTIMOS TURNOS",
        "action_label": "AÇÃO DO JOGADOR",
        "narration_label": "NARRAÇÃO",
    },
    "en": {
        "system": (
            "Judge each condition against what actually happened. Respond "
            'only with the JSON object {"verdicts": [{"id": "...", "met": '
            'true|false}]}, using only ids from the given candidate list. '
            "Mark met: true only when the condition is actually satisfied in "
            "the history shown, never by intent or probability. No prose."
        ),
        "candidates_label": "CANDIDATES",
        "window_label": "RECENT TURNS",
        "action_label": "PLAYER ACTION",
        "narration_label": "NARRATION",
    },
}


class AchievementError(Exception):
    pass


class AchievementVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    met: bool


class AchievementsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[AchievementVerdict]


class AchievementRejection(BaseModel):
    id: str
    reason: str


ACHIEVEMENTS_OPTIONS = GenerationOptions(
    max_tokens=250,
    temperature=0.1,
    timeout_s=45.0,
    json_schema=AchievementsResponse.model_json_schema(),
    schema_name="achievements",
)


def _field(value: str) -> str:
    return " ".join(value.split()).replace("|", "/")


def _stat_value(hud: HudState, stat_id: str) -> int | None:
    if stat_id in hud.stats:
        return hud.stats[stat_id]
    dynamic = hud.dynamic_stats.get(stat_id)
    if dynamic is not None:
        return dynamic.value
    return None


def eligible(
    achievements: list[AchievementDef], hud: HudState, unlocked_ids: Iterable[str]
) -> list[AchievementDef]:
    unlocked = set(unlocked_ids)
    candidates = []
    for achievement in achievements:
        if achievement.id in unlocked:
            continue
        if achievement.min_turn is not None and hud.turn < achievement.min_turn:
            continue
        gates_ok = True
        for gate in achievement.stat_gates:
            value = _stat_value(hud, gate.id)
            if value is None or value < gate.at_least:
                gates_ok = False
                break
        if not gates_ok:
            continue
        candidates.append(achievement)
    return candidates


def build_achievement_messages(
    scenario: LoadedScenario,
    candidates: list[AchievementDef],
    message: str,
    narrator_text: str,
    window: list[ChatMessage],
) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])

    sent = candidates[:MAX_CANDIDATES_PER_CALL]
    candidate_lines = [f"{c.id} | {c.type} | {_field(c.condition)}" for c in sent]

    recent = window[-(ACHIEVEMENT_WINDOW_TURNS * 2) :] if window else []
    window_lines = [f"{m.role}: {m.content[:ACHIEVEMENT_EXCERPT_CHARS]}" for m in recent]

    body_lines = [
        f"[{template['candidates_label']}]",
        *candidate_lines,
        f"[{template['window_label']}]",
        *window_lines,
        f"{template['action_label']}: {message}",
        f"[{template['narration_label']}]",
        narrator_text,
    ]

    return [
        ChatMessage(role="system", content=template["system"]),
        ChatMessage(role="user", content="\n".join(body_lines)),
    ]


def parse_achievements(raw: str) -> tuple[list[dict] | None, str | None]:
    """Tolerant parse: accepts the envelope or a raw list, either bare or code-fenced."""
    text = raw.strip()
    if not text:
        return None, "invalid_json"

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        brace_start = text.find("{")
        bracket_start = text.find("[")
        candidates = [pos for pos in (brace_start, bracket_start) if pos != -1]
        if not candidates:
            return None, "invalid_json"
        start = min(candidates)
        opener = text[start]
        closer = "}" if opener == "{" else "]"
        end = text.rfind(closer)
        if end == -1 or end < start:
            return None, "invalid_json"
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None, "invalid_json"

    if isinstance(data, list):
        return data, None
    if isinstance(data, dict):
        verdicts = data.get("verdicts")
        if isinstance(verdicts, list):
            return verdicts, None
        return None, "invalid_json"

    return None, "invalid_json"


def apply_verdicts(
    candidates: list[AchievementDef], verdicts: list[dict]
) -> tuple[list[AchievementDef], list[AchievementRejection]]:
    by_id = {c.id: c for c in candidates}
    met_ids: dict[str, bool] = {}
    seen_ids: set[str] = set()
    rejections: list[AchievementRejection] = []

    for entry in verdicts:
        if not isinstance(entry, dict):
            rejections.append(AchievementRejection(id="", reason="invalid_shape"))
            continue

        entry_id = entry.get("id")
        if not isinstance(entry_id, str):
            rejections.append(AchievementRejection(id="", reason="invalid_shape"))
            continue

        if entry_id not in by_id:
            rejections.append(AchievementRejection(id=entry_id, reason="not_a_candidate"))
            continue

        if entry_id in seen_ids:
            rejections.append(AchievementRejection(id=entry_id, reason="duplicate_id"))
            continue
        seen_ids.add(entry_id)

        met = entry.get("met")
        if type(met) is not bool:
            rejections.append(AchievementRejection(id=entry_id, reason="not_a_bool"))
            continue

        met_ids[entry_id] = met

    unlocked: list[AchievementDef] = []
    ending_taken = False
    for candidate in candidates:
        if not met_ids.get(candidate.id):
            continue
        if candidate.type == "ending":
            if ending_taken:
                rejections.append(AchievementRejection(id=candidate.id, reason="another_ending"))
                continue
            ending_taken = True
        unlocked.append(candidate)

    return unlocked, rejections


async def judge_achievements(
    scenario: LoadedScenario,
    candidates: list[AchievementDef],
    message: str,
    narrator_text: str,
    window: list[ChatMessage],
    config: Config,
) -> tuple[list[dict] | None, str | None, str]:
    if not candidates:
        raise AchievementError("no candidates")

    try:
        role = config.models["utility"]
    except KeyError:
        raise AchievementError("no utility role") from None

    provider = OpenAICompatProvider(config.providers[role.provider], ACHIEVEMENTS_OPTIONS)
    messages = build_achievement_messages(scenario, candidates, message, narrator_text, window)

    try:
        raw = await provider.complete(messages, role.model)
    except Exception as exc:
        raise AchievementError(str(exc)) from exc

    verdicts, reason = parse_achievements(raw)
    return verdicts, reason, raw
