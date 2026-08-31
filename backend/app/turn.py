from __future__ import annotations

import time
from collections.abc import AsyncIterator

from app.compact import (
    COMPACT_KEEP_TURNS,
    CompactError,
    compact_block,
    estimate_tokens,
    fits,
    select_window,
)
from app.config import load_config
from app.hud import advance
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
from app.observability import emit
from app.prompt import MASTER_PROMPT_VERSION, build_master_prompt
from app.scenario import Character, LoadedScenario, StartConfig, load_scenario
from app.sessions import (
    Event,
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


def history_events(session_id: str, compact_seq: int | None) -> list[Event]:
    """All turn events with seq > compact_seq, in order. Never truncates."""
    events = read_events(session_id, kinds=("player_turn", "narrator_turn"))
    if compact_seq is None:
        return events
    return [event for event in events if event.seq > compact_seq]


def events_to_messages(events: list[Event]) -> list[ChatMessage]:
    """1:1, order-preserving mapping: player_turn -> user, narrator_turn -> assistant."""
    messages = []
    for event in events:
        role = "user" if event.kind == "player_turn" else "assistant"
        messages.append(ChatMessage(role=role, content=event.payload["text"]))
    return messages


def build_context(
    session_id: str,
    message: str,
    compact: str | None = None,
    compact_seq: int | None = None,
    *,
    history: list[Event] | None = None,
) -> list[ChatMessage]:
    row = get_session_row(session_id)
    scenario = load_scenario(row.scenario_id)
    try:
        start = scenario.starts[row.start_id]
    except KeyError:
        raise ScenarioNotFound(row.scenario_id) from None

    characters = _characters_in_scene(scenario, start)
    system = build_master_prompt(scenario, start, row.hud, characters, compact)

    if history is None:
        events = history_events(session_id, None)
        windowed = events[-(WINDOW_TURNS * 2) :]
    else:
        windowed = history

    messages = [ChatMessage(role="system", content=system)]
    messages.extend(events_to_messages(windowed))
    messages.append(ChatMessage(role="user", content=message))
    return messages


async def _maybe_compact(
    session_id: str, message: str, config, locale: str
) -> tuple[list[ChatMessage], str | None]:
    if not config.flag("compact"):
        return build_context(session_id, message), None

    current_compact, current_seq = get_compact(session_id)
    full = history_events(session_id, current_seq)
    messages = build_context(
        session_id, message, compact=current_compact, compact_seq=current_seq, history=full
    )

    n = select_window(messages[0], messages[1:-1], messages[-1], WINDOW_TURNS, COMPACT_KEEP_TURNS)
    if n == 0:
        return messages, None

    outgoing = messages[1 : 1 + n]

    started = time.monotonic()
    error: str | None = None
    new_compact = None
    try:
        new_compact = await compact_block(current_compact, outgoing, locale)
    except CompactError as exc:
        error = str(exc)
        messages = [messages[0], *messages[1 + n :]]
    else:
        from_seq = full[0].seq
        covered_seq = full[n - 1].seq
        set_compact(
            session_id,
            new_compact,
            covered_seq,
            {"replaced_turns": n // 2, "from_seq": from_seq, "to_seq": covered_seq},
        )
        messages = build_context(
            session_id, message, compact=new_compact, compact_seq=covered_seq, history=full[n:]
        )
        if not fits(messages):
            body = messages[1:-1]
            dropped = 0
            while len(body) >= 2 and not fits([messages[0], *body, messages[-1]]):
                body = body[2:]
                dropped += 2
            messages = [messages[0], *body, messages[-1]]
            emit(
                "compact_overflow",
                session_id=session_id,
                dropped_turns=dropped // 2,
                compact_tokens=estimate_tokens(new_compact),
            )

    emit(
        "compact_run",
        session_id=session_id,
        turns_summarized=n // 2,
        in_tokens=sum(estimate_tokens(m.content) for m in outgoing),
        out_tokens=0 if error else estimate_tokens(new_compact),
        duration_ms=int((time.monotonic() - started) * 1000),
        error=error,
        from_seq=None if error else full[0].seq,
        to_seq=None if error else full[n - 1].seq,
        covered_seq=None if error else full[n - 1].seq,
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
