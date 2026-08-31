from __future__ import annotations

import time
from collections.abc import AsyncIterator

from app.compact import CompactError, compact_block, estimate_tokens, fits
from app.config import load_config
from app.hud import advance
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
from app.observability import emit
from app.prompt import MASTER_PROMPT_VERSION, build_master_prompt
from app.scenario import Character, LoadedScenario, StartConfig, load_scenario
from app.sessions import (
    ScenarioNotFound,
    append_events,
    get_compact,
    get_session_row,
    read_events,
    set_compact,
)
from app.tags import parse_tags

WINDOW_TURNS = 18


def _characters_in_scene(scenario: LoadedScenario, start: StartConfig) -> list[Character]:
    if start.characters is None:
        return list(scenario.characters.values())
    return [scenario.characters[char_id] for char_id in start.characters]


def build_context(session_id: str, message: str, compact: str | None = None) -> list[ChatMessage]:
    row = get_session_row(session_id)
    scenario = load_scenario(row.scenario_id)
    try:
        start = scenario.starts[row.start_id]
    except KeyError:
        raise ScenarioNotFound(row.scenario_id) from None

    characters = _characters_in_scene(scenario, start)
    system = build_master_prompt(scenario, start, row.hud, characters, compact)

    events = read_events(session_id, kinds=("player_turn", "narrator_turn"))
    windowed = events[-(WINDOW_TURNS * 2) :]

    messages = [ChatMessage(role="system", content=system)]
    for event in windowed:
        role = "user" if event.kind == "player_turn" else "assistant"
        messages.append(ChatMessage(role=role, content=event.payload["text"]))
    messages.append(ChatMessage(role="user", content=message))
    return messages


def _shrink_to_fit(messages: list[ChatMessage]) -> tuple[list[ChatMessage], list[ChatMessage]]:
    """Drop the oldest turn pairs from the window until the messages fit the budget."""
    system, *history, tail = messages
    outgoing: list[ChatMessage] = []
    while len(history) >= 2 and not fits([system, *history, tail]):
        outgoing.extend(history[:2])
        history = history[2:]
    return [system, *history, tail], outgoing


async def _maybe_compact(
    session_id: str, message: str, config, locale: str
) -> tuple[list[ChatMessage], str | None]:
    current_compact = get_compact(session_id) if config.flag("compact") else None
    messages = build_context(session_id, message, compact=current_compact)

    if not config.flag("compact") or fits(messages):
        return messages, None

    trimmed, outgoing = _shrink_to_fit(messages)
    if not outgoing:
        return trimmed, None

    started = time.monotonic()
    error: str | None = None
    try:
        new_compact = await compact_block(current_compact, outgoing, locale)
    except CompactError as exc:
        error = str(exc)
        messages = trimmed
    else:
        set_compact(
            session_id,
            new_compact,
            {"replaced_turns": len(outgoing) // 2, "from_index": 0, "to_index": len(outgoing) // 2},
        )
        messages = build_context(session_id, message, compact=new_compact)
        if not fits(messages):
            messages, _ = _shrink_to_fit(messages)

    emit(
        "compact_run",
        session_id=session_id,
        turns_summarized=len(outgoing) // 2,
        in_tokens=sum(estimate_tokens(m.content) for m in outgoing),
        out_tokens=0 if error else estimate_tokens(new_compact),
        duration_ms=int((time.monotonic() - started) * 1000),
        error=error,
    )
    return messages, error


async def run_turn(session_id: str, message: str) -> AsyncIterator[dict]:
    config = load_config()
    role = config.models["narrator"]
    provider = OpenAICompatProvider(config.providers[role.provider])

    row = get_session_row(session_id)
    scenario = load_scenario(row.scenario_id)
    messages, _compact_error = await _maybe_compact(session_id, message, config, scenario.meta.locale)
    hud = row.hud

    emit(
        "context_budget",
        session_id=session_id,
        estimated_tokens=sum(estimate_tokens(m.content) for m in messages),
        window_turns=len(messages[1:-1]) // 2,
    )

    started = time.monotonic()
    raw_text = ""
    error: str | None = None
    try:
        async for delta in provider.stream_chat(messages, role.model):
            raw_text += delta
            yield {"delta": delta}
    except Exception as exc:
        error = str(exc)

    tags = []
    clean_text = ""
    if error is None:
        clean_text, tags = parse_tags(raw_text)
        if not clean_text.strip():
            error = "empty turn"

    new_hud = hud
    if error is None:
        new_hud = advance(hud)
        events = [
            ("player_turn", {"text": message}),
            ("narrator_turn", {"text": clean_text}),
        ]
        for tag in tags:
            events.append(("tag", {"kind": tag.kind, "args": tag.args, "raw": tag.raw, "valid": tag.valid}))
        try:
            append_events(session_id, events, hud=new_hud)
        except Exception as exc:
            error = str(exc)
            new_hud = hud

    if error is None:
        yield {"hud": new_hud.model_dump()}
    else:
        yield {"error": error}

    emit(
        "game_turn",
        session_id=session_id,
        turn=new_hud.turn,
        model=role.model,
        prompt_version=MASTER_PROMPT_VERSION,
        duration_ms=int((time.monotonic() - started) * 1000),
        chars=len(raw_text),
        tags=len(tags),
        invalid_tags=sum(1 for tag in tags if not tag.valid),
        error=error,
    )
