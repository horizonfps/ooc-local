from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.config import Config
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import LoadedScenario
from app.sessions import read_events

MEMORY_EVENT_KIND = "memory"
MEMORY_CHECK_EVERY = 3
MEMORY_WINDOW_TURNS = 6
MEMORY_TEXT_CHARS = 200
MEMORY_RAW_LOG_CHARS = 200

USER_NOTE_CATEGORY = "user_note"
EXTRACTED_CATEGORIES = ("long_term", "relationship", "goal", "temporary")
MEMORY_CATEGORIES = (*EXTRACTED_CATEGORIES, USER_NOTE_CATEGORY)
MEMORY_CAPS = {
    "long_term": 12, "relationship": 12, "goal": 6, "temporary": 4, "user_note": 1,
}

_ID_RE = re.compile(r"^[a-z0-9-]+$")


class MemoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: Literal["long_term", "relationship", "goal", "temporary", "user_note"]
    text: str
    turn: int
    source: Literal["engine", "player"] = "engine"


class MemoryRejection(BaseModel):
    id: str
    reason: str


class MemoryError(Exception):
    pass


MEMORIES_SCHEMA = {
    "type": "object",
    "properties": {
        "entries": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "category": {"type": "string"},
                    "text": {"type": "string"},
                },
            },
        }
    },
}
MEMORY_OPTIONS = GenerationOptions(
    max_tokens=400,
    temperature=0.2,
    timeout_s=60.0,
    json_schema=MEMORIES_SCHEMA,
    schema_name="memories",
    reasoning_effort="low",
)

_PROMPT_TEMPLATES = {
    "pt-br": {
        "system": (
            "Responda apenas o objeto JSON "
            '{"entries": [{"id": "...", "category": "...", "text": "..."}]} '
            "com fatos novos ou atualizados desta partida. Categorias válidas: "
            f"{', '.join(EXTRACTED_CATEGORIES)}. id em minúsculas, letras, "
            "números e hífen, curto e estável entre chamadas para a mesma "
            f"memória. text com no máximo {MEMORY_TEXT_CHARS} caracteres, "
            "afirmando o fato direto, sem opinião. Liste só memórias novas ou "
            "que mudaram; entries vazio quando nada mudou. Sem prosa."
        ),
        "current_label": "MEMÓRIAS VIGENTES",
        "action_label": "AÇÃO DO JOGADOR",
        "narration_label": "NARRAÇÃO",
    },
    "en": {
        "system": (
            "Respond only with the JSON object "
            '{"entries": [{"id": "...", "category": "...", "text": "..."}]} '
            "with new or updated facts from this playthrough. Valid "
            f"categories: {', '.join(EXTRACTED_CATEGORIES)}. id lowercase, "
            "letters, digits and hyphen, short and stable across calls for "
            f"the same memory. text at most {MEMORY_TEXT_CHARS} characters, "
            "stating the fact directly, no opinion. List only new or changed "
            "memories; empty entries when nothing changed. No prose."
        ),
        "current_label": "CURRENT MEMORIES",
        "action_label": "PLAYER ACTION",
        "narration_label": "NARRATION",
    },
}

_CATEGORY_LABELS = {
    "pt-br": {
        "long_term": "Fatos permanentes",
        "relationship": "Relações",
        "goal": "Objetivos",
        "temporary": "Estado passageiro",
        "user_note": "Nota do jogador (escrita por ele mesmo)",
    },
    "en": {
        "long_term": "Permanent facts",
        "relationship": "Relationships",
        "goal": "Goals",
        "temporary": "Temporary state",
        "user_note": "Player's note (written by the player)",
    },
}

_MEMORY_ORDER = ("long_term", "relationship", "goal", "temporary", "user_note")


def read_memories(session_id: str) -> list[MemoryEntry]:
    """Last memory event's entries, validated item by item. A malformed
    payload or entry is dropped, never raised, so a corrupt event can't take
    down GET /api/sessions/{id} or the next turn."""
    events = read_events(session_id, kinds=(MEMORY_EVENT_KIND,))
    if not events:
        return []
    raw_entries = events[-1].payload.get("entries")
    if not isinstance(raw_entries, list):
        return []
    result: list[MemoryEntry] = []
    for item in raw_entries:
        try:
            result.append(MemoryEntry.model_validate(item))
        except Exception:
            continue
    return result


def build_memory_messages(
    scenario: LoadedScenario,
    memories: list[MemoryEntry],
    window: list[ChatMessage],
    message: str,
    narrator_text: str,
) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])

    lines = [f"[{template['current_label']}]"]
    for memory in memories:
        lines.append(f"{memory.id} | {memory.category} | {memory.text}")

    for entry in window:
        role_label = template["action_label"] if entry.role == "user" else template["narration_label"]
        lines.append(f"[{role_label}] {entry.content}")

    lines.append(f"{template['action_label']}: {message}")
    lines.append(f"[{template['narration_label']}]")
    lines.append(narrator_text)

    return [
        ChatMessage(role="system", content=template["system"]),
        ChatMessage(role="user", content="\n".join(lines)),
    ]


def _loads_tolerant(text: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end >= start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def parse_memories(raw: str) -> tuple[list | None, str | None]:
    """Tolerant parse: local models often wrap the object in code fences or prose."""
    text = raw.strip()
    if not text:
        return None, "invalid_json"

    data = _loads_tolerant(text)
    if not isinstance(data, dict):
        return None, "invalid_json"

    entries = data.get("entries")
    if not isinstance(entries, list):
        return None, "invalid_json"

    return entries, None


def merge_memories(
    previous: list[MemoryEntry], proposed: list, turn: int
) -> tuple[list[MemoryEntry], list[MemoryRejection], list[MemoryEntry]]:
    by_id = {entry.id: entry for entry in previous}
    rejections: list[MemoryRejection] = []

    for item in proposed:
        if not isinstance(item, dict):
            rejections.append(MemoryRejection(id="", reason="invalid_shape"))
            continue
        entry_id = item.get("id")
        category = item.get("category")
        text = item.get("text")

        if not isinstance(entry_id, str) or not _ID_RE.match(entry_id):
            rejections.append(MemoryRejection(id=str(entry_id), reason="invalid_id"))
            continue
        if category not in EXTRACTED_CATEGORIES:
            rejections.append(MemoryRejection(id=entry_id, reason="invalid_category"))
            continue
        if not isinstance(text, str) or not text.strip():
            rejections.append(MemoryRejection(id=entry_id, reason="empty"))
            continue

        existing = by_id.get(entry_id)
        if existing is not None and existing.source == "player":
            rejections.append(MemoryRejection(id=entry_id, reason="player_owned"))
            continue

        clamped_text = " ".join(text.split())[:MEMORY_TEXT_CHARS]
        if existing is not None and existing.category == category and existing.text == clamped_text:
            rejections.append(MemoryRejection(id=entry_id, reason="duplicate"))
            continue

        by_id[entry_id] = MemoryEntry(
            id=entry_id, category=category, text=clamped_text, turn=turn, source="engine"
        )

    evicted: list[MemoryEntry] = []
    by_category: dict[str, list[MemoryEntry]] = {category: [] for category in MEMORY_CATEGORIES}
    for entry in by_id.values():
        by_category.setdefault(entry.category, []).append(entry)

    entries: list[MemoryEntry] = []
    for category, category_entries in by_category.items():
        cap = MEMORY_CAPS.get(category, len(category_entries))
        category_entries.sort(key=lambda entry: entry.turn)
        while len(category_entries) > cap:
            evicted.append(category_entries.pop(0))
        entries.extend(category_entries)

    return entries, rejections, evicted


def memory_event(entries: list[MemoryEntry]) -> tuple[str, dict]:
    return MEMORY_EVENT_KIND, {"entries": [entry.model_dump() for entry in entries]}


def render_memories(memories: list[MemoryEntry], locale: str) -> str | None:
    if not memories:
        return None
    labels = _CATEGORY_LABELS.get(locale, _CATEGORY_LABELS["pt-br"])

    by_category: dict[str, list[MemoryEntry]] = {}
    for entry in memories:
        by_category.setdefault(entry.category, []).append(entry)

    parts = []
    for category in _MEMORY_ORDER:
        category_entries = by_category.get(category)
        if not category_entries:
            continue
        lines = "\n".join(f"- {entry.text}" for entry in category_entries)
        parts.append(f"{labels[category]}:\n{lines}")

    return "\n\n".join(parts)


async def extract_memories(
    scenario: LoadedScenario,
    memories: list[MemoryEntry],
    window: list[ChatMessage],
    message: str,
    narrator_text: str,
    config: Config,
) -> tuple[list | None, str | None, str]:
    try:
        role = config.models["utility"]
    except KeyError:
        raise MemoryError("no utility role") from None

    provider = OpenAICompatProvider(config.providers[role.provider], MEMORY_OPTIONS)
    messages = build_memory_messages(scenario, memories, window, message, narrator_text)

    try:
        raw = await provider.complete(messages, role.model)
    except Exception as exc:
        raise MemoryError(str(exc)) from exc

    proposed, reason = parse_memories(raw)
    return proposed, reason, raw
