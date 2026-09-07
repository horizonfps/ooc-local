from __future__ import annotations

import math

from pydantic import BaseModel

from app.config import load_config
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import OpenAICompatProvider
from app.sessions import read_events

CONTEXT_BUDGET_TOKENS = 24_000
OUTPUT_RESERVE_TOKENS = 800
COMPACT_TARGET_TOKENS = 400

INPUT_BUDGET_TOKENS = CONTEXT_BUDGET_TOKENS - OUTPUT_RESERVE_TOKENS

COMPACT_KEEP_TURNS = 9
COMPACT_RESERVE_TOKENS = 700

COMPACT_MAX_BLOCKS = 4
COMPACT_MERGE_BLOCKS = 2
COMPACT_COMPOSED_MAX_TOKENS = COMPACT_TARGET_TOKENS * COMPACT_MAX_BLOCKS

COMPACT_MAX_TOKENS = 400
COMPACT_OPTIONS = GenerationOptions(
    max_tokens=COMPACT_MAX_TOKENS, temperature=0.2, timeout_s=180.0, reasoning_effort="low"
)

_PROMPT_TEMPLATES = {
    "pt-br": {
        "system": (
            "Resuma em terceira pessoa, em português do Brasil, o histórico de jogo "
            f"abaixo em no máximo {COMPACT_TARGET_TOKENS} tokens. Foque em promessas "
            "feitas, conflitos abertos e mudanças de relação entre personagens. Não "
            "invente fatos e não reproduza diálogo literal."
        ),
        "previous_label": "RESUMO ANTERIOR",
        "outgoing_label": "TURNOS QUE SAEM DA JANELA",
        "blocks_label": "TURNOS ANTERIORES",
    },
    "en": {
        "system": (
            "Summarize the game history below in third person, in English, in at "
            f"most {COMPACT_TARGET_TOKENS} tokens. Focus on promises made, open "
            "conflicts and changes in relationships between characters. Do not "
            "invent facts and do not reproduce literal dialogue."
        ),
        "previous_label": "PREVIOUS SUMMARY",
        "outgoing_label": "TURNS LEAVING THE WINDOW",
        "blocks_label": "EARLIER TURNS",
    },
}


class CompactError(Exception):
    pass


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def fits(messages: list[ChatMessage]) -> bool:
    total = sum(estimate_tokens(message.content) for message in messages)
    return total <= INPUT_BUDGET_TOKENS


def select_window(
    system: ChatMessage,
    history: list[ChatMessage],
    tail: ChatMessage,
    window_turns: int,
    keep_turns: int,
    reserve_tokens: int = COMPACT_RESERVE_TOKENS,
) -> int:
    """How many messages leave the START of history. Always even.

    Decides the cutoff in a single pass: count trigger first (hysteresis down
    to keep_turns pairs), then budget trigger on top of it. 0 means no
    compaction. The window is never emptied: at least one pair always stays.
    """
    n = 0

    if len(history) // 2 > window_turns:
        while (len(history) - n) // 2 > keep_turns:
            n += 2

    placeholder = ChatMessage(role="system", content="x" * (reserve_tokens * 4))
    while (len(history) - n) // 2 > 1 and not fits([system, *history[n:], tail, placeholder]):
        n += 2

    return n


def _build_prompt(previous: str | None, outgoing: list[ChatMessage], locale: str) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(locale, _PROMPT_TEMPLATES["pt-br"])

    body_lines = []
    if previous:
        body_lines.append(f"[{template['previous_label']}]\n{previous}")
    body_lines.append(f"[{template['outgoing_label']}]")
    for message in outgoing:
        body_lines.append(f"{message.role}: {message.content}")

    return [
        ChatMessage(role="system", content=template["system"]),
        ChatMessage(role="user", content="\n".join(body_lines)),
    ]


async def compact_block(previous: str | None, outgoing: list[ChatMessage], locale: str) -> str:
    config = load_config()
    role = config.models["utility"]
    provider = OpenAICompatProvider(config.providers[role.provider], COMPACT_OPTIONS)

    prompt_messages = _build_prompt(previous, outgoing, locale)
    try:
        text = await provider.complete(prompt_messages, role.model)
    except Exception as exc:
        raise CompactError(str(exc)) from exc

    text = text.strip()
    if not text:
        raise CompactError("utility returned an empty compact")
    return text


class CompactBlock(BaseModel):
    text: str
    from_seq: int
    to_seq: int
    level: int = 1


def read_blocks(session_id: str, fallback_text: str | None) -> list[CompactBlock]:
    """Blocks stacked from `compact` events, defensive item by item like
    read_minds: a malformed payload is dropped, never raised. Level-2 blocks
    replace the level-1 blocks whose range they contain. Falls back to a
    single block wrapping the legacy `sessions.compact` column when there is
    no event at all."""
    events = read_events(session_id, kinds=("compact",))
    raw: list[CompactBlock] = []
    for event in events:
        payload = event.payload
        text = payload.get("text")
        from_seq = payload.get("from_seq")
        to_seq = payload.get("to_seq")
        if not isinstance(text, str) or not isinstance(from_seq, int) or not isinstance(to_seq, int):
            continue
        level = payload.get("level", 1)
        if not isinstance(level, int):
            level = 1
        raw.append(CompactBlock(text=text, from_seq=from_seq, to_seq=to_seq, level=level))

    layers = [block for block in raw if block.level != 1]
    blocks = list(layers)
    for block in raw:
        if block.level != 1:
            continue
        covered = any(
            layer.from_seq <= block.from_seq and block.to_seq <= layer.to_seq for layer in layers
        )
        if not covered:
            blocks.append(block)

    if not blocks and fallback_text is not None:
        return [CompactBlock(text=fallback_text, from_seq=0, to_seq=0, level=1)]

    return blocks


def compose(blocks: list[CompactBlock], locale: str) -> str:
    """Deterministic composition, oldest to newest, no network call. A single
    block is returned as-is so a legacy or first-compaction session keeps the
    exact text its consumers already expect."""
    if not blocks:
        return ""

    ordered = sorted(blocks, key=lambda block: block.from_seq)
    if len(ordered) == 1:
        return ordered[0].text

    template = _PROMPT_TEMPLATES.get(locale, _PROMPT_TEMPLATES["pt-br"])
    label = template["blocks_label"]
    return "\n\n".join(f"[{label}]\n{block.text}" for block in ordered)


def needs_merge(blocks: list[CompactBlock]) -> bool:
    return sum(1 for block in blocks if block.level == 1) > COMPACT_MAX_BLOCKS


async def merge_oldest(blocks: list[CompactBlock], locale: str) -> CompactBlock:
    """Folds the COMPACT_MERGE_BLOCKS oldest level-1 blocks into one level-2
    layer, with one utility call."""
    level1 = sorted((block for block in blocks if block.level == 1), key=lambda block: block.from_seq)
    oldest = level1[:COMPACT_MERGE_BLOCKS]
    outgoing = [ChatMessage(role="system", content=block.text) for block in oldest]
    text = await compact_block(None, outgoing, locale)
    return CompactBlock(text=text, from_seq=oldest[0].from_seq, to_seq=oldest[-1].to_seq, level=2)
