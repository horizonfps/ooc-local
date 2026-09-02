from __future__ import annotations

import time
from collections.abc import AsyncIterator

from pydantic import BaseModel

from app.cast import MindView, cast_event, minds_event, resolve_cast, seed_cast_ids
from app.cleanup import strip_engine_echo
from app.compact import (
    COMPACT_KEEP_TURNS,
    CompactError,
    compact_block,
    estimate_tokens,
    fits,
    select_window,
)
from app.config import Config, load_config
from app.director import DIRECTOR_RAW_LOG_CHARS, DIRECTOR_WINDOW_TURNS, DirectorError, decide_scene
from app.hud import advance, apply_location, apply_stat, ensure_stats, stat_event, stat_ids, stat_views
from app.judge import JUDGE_RAW_LOG_CHARS, JudgeError, apply_judgement, judge_turn
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
from app.minds import MINDS_RAW_LOG_CHARS, MindsError, merge_minds, think_minds
from app.observability import emit
from app.prompt import MASTER_PROMPT_VERSION, build_master_prompt
from app.scenario import Character, LoadedScenario, ScenarioError, StartConfig, load_scenario
from app.sessions import (
    Event,
    ScenarioNotFound,
    SessionRow,
    append_events,
    get_compact,
    get_session_row,
    read_cast_ids,
    read_events,
    read_minds,
    set_compact,
)
from app.tags import Tag, parse_tags

WINDOW_TURNS = 18
TURN_ERROR_CODE = "turn_failed"


class TurnContext(BaseModel):
    row: SessionRow
    scenario: LoadedScenario
    start: StartConfig
    characters: list[Character]
    cast_ids: list[str]
    minds: dict[str, MindView] = {}


def load_turn_context(session_id: str) -> TurnContext:
    """Single point that reads the session row and loads its scenario for a turn."""
    row = get_session_row(session_id)
    try:
        scenario = load_scenario(row.scenario_id)
        start = scenario.starts[row.start_id]
    except (ScenarioError, KeyError):
        raise ScenarioNotFound(row.scenario_id) from None

    ids = read_cast_ids(session_id)
    if ids is None:
        ids = seed_cast_ids(scenario, start)
    else:
        ids = [char_id for char_id in ids if char_id in scenario.characters]
    characters = [scenario.characters[char_id] for char_id in ids]
    row = row.model_copy(update={"hud": ensure_stats(row.hud, scenario.stats)})
    minds = read_minds(session_id)
    return TurnContext(
        row=row, scenario=scenario, start=start, characters=characters, cast_ids=ids, minds=minds
    )


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
    ctx: TurnContext | None = None,
) -> list[ChatMessage]:
    if ctx is None:
        ctx = load_turn_context(session_id)

    system = build_master_prompt(ctx.scenario, ctx.start, ctx.row.hud, ctx.characters, compact, ctx.minds)

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
    session_id: str,
    message: str,
    config: Config,
    locale: str,
    ctx: TurnContext,
) -> tuple[list[ChatMessage], str | None]:
    if not config.flag("compact"):
        return build_context(session_id, message, ctx=ctx), None

    current_compact, current_seq = get_compact(session_id)
    full = history_events(session_id, current_seq)
    messages = build_context(
        session_id, message, compact=current_compact, compact_seq=current_seq, history=full, ctx=ctx
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
            session_id, message, compact=new_compact, compact_seq=covered_seq, history=full[n:], ctx=ctx
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


async def run_turn(
    session_id: str,
    message: str,
    *,
    ctx: TurnContext | None = None,
    config: Config | None = None,
) -> AsyncIterator[dict]:
    """Async generator; the entire body up to persistence is guarded so any exception
    still reaches `game_turn` before propagating to the caller's stream wrapper."""
    started = time.monotonic()
    raw_text = ""
    hud = None
    role_model = None
    tags = []
    stripped_lines = 0
    location_changed = False
    stat_change_count = 0
    suggestion_count = 0

    def emit_game_turn(error: str | None) -> None:
        emit(
            "game_turn",
            session_id=session_id,
            turn=hud.turn if hud is not None else None,
            model=role_model,
            prompt_version=MASTER_PROMPT_VERSION,
            duration_ms=int((time.monotonic() - started) * 1000),
            chars=len(raw_text),
            tags=len(tags),
            invalid_tags=sum(1 for tag in tags if not tag.valid),
            stripped_lines=stripped_lines,
            location_changed=location_changed,
            error=error,
            cast=len(ctx.cast_ids) if ctx is not None else None,
            stats=stat_change_count if ctx is not None else None,
            suggestions=suggestion_count if ctx is not None else None,
        )

    pending_cast_event: tuple[str, dict] | None = None
    pending_minds_event: tuple[str, dict] | None = None

    try:
        if config is None:
            config = load_config()
        if ctx is None:
            ctx = load_turn_context(session_id)
        role = config.models["narrator"]
        role_model = role.model
        provider = OpenAICompatProvider(config.providers[role.provider])

        if config.flag("director"):
            director_started = time.monotonic()
            decision = None
            try:
                window = events_to_messages(
                    history_events(session_id, None)[-(DIRECTOR_WINDOW_TURNS * 2) :]
                )
                decision = await decide_scene(
                    ctx.scenario, ctx.row.hud, ctx.cast_ids, message, window, config
                )
            except DirectorError as exc:
                emit(
                    "director_failed",
                    session_id=session_id,
                    turn=ctx.row.hud.turn,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - director_started) * 1000),
                )
            except Exception as exc:  # defensive: local providers return creative garbage
                emit(
                    "director_failed",
                    session_id=session_id,
                    turn=ctx.row.hud.turn,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - director_started) * 1000),
                )
            if decision is not None:
                ids, reason, raw = decision
                director_duration_ms = int((time.monotonic() - director_started) * 1000)
                if ids is not None:
                    before = ctx.cast_ids
                    if ids != before:
                        new_characters = [
                            ctx.scenario.characters[char_id]
                            for char_id in ids
                            if char_id in ctx.scenario.characters
                        ]
                        ctx = ctx.model_copy(update={"cast_ids": ids, "characters": new_characters})
                        pending_cast_event = cast_event(ids, "director")
                    emit(
                        "director_applied",
                        session_id=session_id,
                        turn=ctx.row.hud.turn,
                        before=before,
                        after=ids,
                        added=[char_id for char_id in ids if char_id not in before],
                        removed=[char_id for char_id in before if char_id not in ids],
                        duration_ms=director_duration_ms,
                        model=config.models["utility"].model,
                    )
                else:
                    emit(
                        "director_rejected",
                        session_id=session_id,
                        turn=ctx.row.hud.turn,
                        reason=reason,
                        raw=raw[:DIRECTOR_RAW_LOG_CHARS],
                        kept=ctx.cast_ids,
                        duration_ms=director_duration_ms,
                    )

        messages, _compact_error = await _maybe_compact(
            session_id, message, config, ctx.scenario.meta.locale, ctx
        )
        hud = ctx.row.hud

        emit(
            "context_budget",
            session_id=session_id,
            estimated_tokens=sum(estimate_tokens(m.content) for m in messages),
            window_turns=len(messages[1:-1]) // 2,
        )

        async for delta in provider.stream_chat(messages, role.model):
            raw_text += delta
            yield {"delta": delta}

        clean_text, tags = parse_tags(raw_text)
        clean_text, stripped_lines = strip_engine_echo(clean_text)
        if not clean_text.strip():
            emit_game_turn("empty turn")
            yield {"error": "empty turn"}
            return

        new_hud = advance(hud)
        for tag in tags:
            if tag.kind == "LOC" and tag.valid:
                new_hud = apply_location(new_hud, tag.args[0])
        location_changed = new_hud.location != hud.location

        known_stat_ids = stat_ids(new_hud, ctx.scenario.stats)
        resolved_tags: list[Tag] = []
        stat_events: list[tuple[str, dict]] = []
        for tag in tags:
            if tag.kind == "STAT" and tag.valid and tag.args[0] not in known_stat_ids:
                tag = tag.model_copy(update={"valid": False})
            elif tag.kind == "STAT" and tag.valid:
                new_hud, change = apply_stat(new_hud, ctx.scenario.stats, tag.args[0], int(tag.args[1]))
                if change is not None:
                    delta, value = change
                    stat_events.append(stat_event(tag.args[0], delta, value, "tag"))
            resolved_tags.append(tag)
        tags = resolved_tags
        touched_ids = [payload["id"] for _kind, payload in stat_events]

        if config.flag("hud_judge"):
            judge_started = time.monotonic()
            try:
                judgement, judge_reason, judge_raw = await judge_turn(
                    ctx.scenario, new_hud, message, clean_text, touched_ids, config
                )
            except JudgeError as exc:
                emit(
                    "judge_failed",
                    session_id=session_id,
                    turn=new_hud.turn,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - judge_started) * 1000),
                )
            except Exception as exc:  # defensive: local providers return creative garbage
                emit(
                    "judge_failed",
                    session_id=session_id,
                    turn=new_hud.turn,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - judge_started) * 1000),
                )
            else:
                judge_duration_ms = int((time.monotonic() - judge_started) * 1000)
                if judgement is not None:
                    new_hud, changes, rejections = apply_judgement(
                        ctx.scenario, new_hud, judgement, touched_ids
                    )
                    stat_events += [
                        stat_event(change.id, change.delta, change.value, change.source)
                        for change in changes
                    ]
                    emit(
                        "judge_applied",
                        session_id=session_id,
                        turn=new_hud.turn,
                        changes=[
                            {"id": change.id, "delta": change.delta, "value": change.value}
                            for change in changes
                        ],
                        rejected=[
                            {"id": rejection.id, "reason": rejection.reason} for rejection in rejections
                        ],
                        duration_ms=judge_duration_ms,
                        model=config.models["utility"].model,
                    )
                else:
                    emit(
                        "judge_rejected",
                        session_id=session_id,
                        turn=new_hud.turn,
                        reason=judge_reason,
                        raw=judge_raw[:JUDGE_RAW_LOG_CHARS],
                        duration_ms=judge_duration_ms,
                    )

        if config.flag("minds"):
            minds_started = time.monotonic()
            try:
                proposed, minds_reason, minds_raw = await think_minds(
                    ctx.scenario, ctx.cast_ids, ctx.minds, message, clean_text, config
                )
            except MindsError as exc:
                emit(
                    "minds_failed",
                    session_id=session_id,
                    turn=new_hud.turn,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - minds_started) * 1000),
                )
            except Exception as exc:  # defensive: local providers return creative garbage
                emit(
                    "minds_failed",
                    session_id=session_id,
                    turn=new_hud.turn,
                    error=str(exc),
                    duration_ms=int((time.monotonic() - minds_started) * 1000),
                )
            else:
                minds_duration_ms = int((time.monotonic() - minds_started) * 1000)
                if proposed is not None:
                    entries, rejections = merge_minds(ctx.minds, proposed, ctx.cast_ids)
                    changed_ids = [
                        char_id
                        for char_id, view in entries.items()
                        if ctx.minds.get(char_id) != view
                    ]
                    if entries != ctx.minds:
                        pending_minds_event = minds_event(entries)
                        ctx = ctx.model_copy(update={"minds": entries})
                    emit(
                        "minds_applied",
                        session_id=session_id,
                        turn=new_hud.turn,
                        ids=list(entries.keys()),
                        changed=changed_ids,
                        rejected=[
                            {"id": rejection.id, "reason": rejection.reason} for rejection in rejections
                        ],
                        duration_ms=minds_duration_ms,
                        model=config.models["utility"].model,
                    )
                else:
                    emit(
                        "minds_rejected",
                        session_id=session_id,
                        turn=new_hud.turn,
                        reason=minds_reason,
                        raw=minds_raw[:MINDS_RAW_LOG_CHARS],
                        duration_ms=minds_duration_ms,
                    )

        stat_change_count = len(stat_events)
        suggestions = [
            ":".join(tag.args).strip() for tag in tags if tag.kind == "SUGGEST" and tag.valid
        ][:3]
        suggestion_count = len(suggestions)

        events = [
            ("player_turn", {"text": message}),
            ("narrator_turn", {"text": clean_text, "suggestions": suggestions}),
        ]
        for tag in tags:
            events.append(("tag", {"kind": tag.kind, "args": tag.args, "raw": tag.raw, "valid": tag.valid}))
        events.extend(stat_events)
        if pending_cast_event is not None:
            events.append(pending_cast_event)
        if pending_minds_event is not None:
            events.append(pending_minds_event)
        append_events(session_id, events, hud=new_hud)

        hud = new_hud
        cast = [member.model_dump() for member in resolve_cast(ctx.scenario, ctx.cast_ids)]
        if suggestions:
            yield {"suggestions": suggestions}
        yield {
            "hud": {
                **new_hud.model_dump(exclude={"stats", "dynamic_stats"}),
                "cast": cast,
                "stats": [view.model_dump() for view in stat_views(ctx.scenario, new_hud)],
                "minds": {char_id: view.model_dump() for char_id, view in ctx.minds.items()},
            }
        }
        emit_game_turn(None)
    except Exception as exc:
        emit_game_turn(str(exc))
        raise
