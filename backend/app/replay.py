from __future__ import annotations

from pydantic import BaseModel

from app.cast import MindView, seed_cast_ids
from app.hud import DynamicStat, HudState, advance, apply_location, ensure_stats, hud_from_start
from app.scenario import LoadedScenario, ScenarioError, StartConfig, load_scenario
from app.sessions import Event, ScenarioNotFound, get_session_row, read_events


class TurnSnapshot(BaseModel):
    seq: int
    turn: int
    message: str
    mode: str | None
    narrator_text: str
    suggestions: list[str]
    hud_start: HudState
    hud_after_tags: HudState
    hud_end: HudState
    touched_ids: list[str]
    cast_before: list[str]
    cast_after: list[str]
    minds_before: dict[str, MindView]
    history_before: list[Event]
    compact: str | None
    compact_seq: int | None
    exact: bool


class SessionReplay(BaseModel):
    session_id: str
    scenario: LoadedScenario
    start: StartConfig
    locale: str
    turns: list[TurnSnapshot]


def _apply_stat_event(
    hud: HudState, scenario: LoadedScenario, event: Event
) -> tuple[HudState, bool]:
    """Writes the persisted value directly, never re-derives it from delta. Returns
    (new_hud, exact): exact is False when the id is a dynamic stat created here
    without its persisted name/min/max (turn.py never wrote them)."""
    stat_id = event.payload.get("id")
    value = event.payload.get("value")
    declared_ids = {stat.id for stat in scenario.stats}
    if stat_id in declared_ids:
        return hud.model_copy(update={"stats": {**hud.stats, stat_id: value}}), True
    if stat_id in hud.dynamic_stats:
        dynamic = hud.dynamic_stats[stat_id].model_copy(update={"value": value})
        return hud.model_copy(update={"dynamic_stats": {**hud.dynamic_stats, stat_id: dynamic}}), True
    dynamic = DynamicStat(name=stat_id, value=value, min=0, max=value)
    return hud.model_copy(update={"dynamic_stats": {**hud.dynamic_stats, stat_id: dynamic}}), False


def replay_session(session_id: str) -> SessionReplay:
    row = get_session_row(session_id)
    try:
        scenario = load_scenario(row.scenario_id)
        start = scenario.starts[row.start_id]
    except (ScenarioError, KeyError):
        raise ScenarioNotFound(row.scenario_id) from None

    events = read_events(session_id)

    hud = ensure_stats(hud_from_start(start), scenario.stats)
    cast_ids = [char_id for char_id in seed_cast_ids(scenario, start) if char_id in scenario.characters]
    minds: dict[str, MindView] = {}
    compact: str | None = None
    compact_seq: int | None = None
    exact = True
    history: list[Event] = []
    turns: list[TurnSnapshot] = []
    group: list[Event] | None = None

    def close_group(group_events: list[Event]) -> None:
        nonlocal hud, cast_ids, minds, exact

        player_event = group_events[0]
        narrator_event = next(
            (event for event in group_events[1:] if event.kind == "narrator_turn"), None
        )
        if narrator_event is None or "text" not in player_event.payload or "text" not in narrator_event.payload:
            exact = False
            return

        hud_start = hud
        cast_before = cast_ids
        minds_before = minds
        history_before = list(history)

        tags = [event for event in group_events[1:] if event.kind == "tag"]
        stat_events = [event for event in group_events[1:] if event.kind == "stat"]
        cast_events = [event for event in group_events[1:] if event.kind == "cast"]
        minds_events = [event for event in group_events[1:] if event.kind == "minds"]

        touched_ids = [
            tag.payload["args"][0]
            for tag in tags
            if tag.payload.get("kind") == "STAT" and tag.payload.get("valid") is True
        ]

        hud_after_tags = advance(hud_start)
        for tag in tags:
            if tag.payload.get("kind") == "LOC" and tag.payload.get("valid") is True:
                hud_after_tags = apply_location(hud_after_tags, tag.payload["args"][0])

        for stat in stat_events:
            if stat.payload.get("source") == "tag":
                hud_after_tags, ok = _apply_stat_event(hud_after_tags, scenario, stat)
                exact = exact and ok

        hud_end = hud_after_tags
        for stat in stat_events:
            if stat.payload.get("source") != "tag":
                hud_end, ok = _apply_stat_event(hud_end, scenario, stat)
                exact = exact and ok

        cast_after = list(cast_events[-1].payload.get("ids", [])) if cast_events else cast_before

        if minds_events:
            entries = minds_events[-1].payload.get("entries", {})
            minds_after = {char_id: MindView.model_validate(value) for char_id, value in entries.items()}
        else:
            minds_after = minds_before

        turns.append(
            TurnSnapshot(
                seq=narrator_event.seq,
                turn=hud_after_tags.turn,
                message=player_event.payload.get("text", ""),
                mode=player_event.payload.get("mode"),
                narrator_text=narrator_event.payload.get("text", ""),
                suggestions=narrator_event.payload.get("suggestions", []),
                hud_start=hud_start,
                hud_after_tags=hud_after_tags,
                hud_end=hud_end,
                touched_ids=touched_ids,
                cast_before=cast_before,
                cast_after=cast_after,
                minds_before=minds_before,
                history_before=history_before,
                compact=compact,
                compact_seq=compact_seq,
                exact=exact,
            )
        )

        history.append(player_event)
        history.append(narrator_event)
        hud = hud_end
        cast_ids = cast_after
        minds = minds_after

    for event in events:
        if event.kind == "compact":
            if group is not None:
                close_group(group)
                group = None
            compact = event.payload.get("text")
            compact_seq = event.payload.get("to_seq")
            continue
        if event.kind in ("player_turn", "meta_player_turn"):
            if group is not None:
                close_group(group)
            group = [event] if event.kind == "player_turn" else None
            continue
        if group is None:
            if event.kind == "narrator_turn":
                exact = False
            continue
        group.append(event)
    if group is not None:
        close_group(group)

    return SessionReplay(
        session_id=session_id,
        scenario=scenario,
        start=start,
        locale=scenario.meta.locale,
        turns=turns,
    )
