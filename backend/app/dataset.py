from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import TextIO

from app.director import DIRECTOR_WINDOW_TURNS, build_director_messages
from app.judge import build_judge_messages
from app.minds import build_minds_messages
from app.replay import SessionReplay, TurnSnapshot, replay_session
from app.sessions import Event, ScenarioNotFound, SessionNotFound, list_sessions, read_events
from app.turn import events_to_messages

TASKS: tuple[str, ...] = ("judge", "director", "minds")
HOLDOUT_PCT = 10


def split_for(session_id: str) -> str:
    bucket = int(hashlib.sha256(session_id.encode()).hexdigest()[:8], 16) % 100
    return "holdout" if bucket < HOLDOUT_PCT else "train"


def _stat_snapshot(hud) -> dict[str, int]:
    merged = dict(hud.stats)
    for stat_id, dynamic in hud.dynamic_stats.items():
        merged[stat_id] = dynamic.value
    return merged


def _judge_engine_label(snap: TurnSnapshot) -> tuple[dict, bool]:
    """hud_end only differs from hud_after_tags by the judge's own stat events
    (replay.py applies tag-sourced stats into hud_after_tags, judge-sourced on top)."""
    before = _stat_snapshot(snap.hud_after_tags)
    after = _stat_snapshot(snap.hud_end)
    stats = {
        stat_id: value - before.get(stat_id, 0)
        for stat_id, value in after.items()
        if value != before.get(stat_id, 0)
    }
    return {"stats": stats}, bool(stats)


def _director_engine_label(snap: TurnSnapshot) -> tuple[dict, bool]:
    return {"scene": snap.cast_after}, snap.cast_after != snap.cast_before


def _minds_engine_label(snap: TurnSnapshot, minds_by_seq: dict[int, dict]) -> tuple[dict, bool]:
    entries = minds_by_seq.get(snap.seq)
    if entries is None:
        return {}, False
    label = {
        char_id: value
        for char_id, value in entries.items()
        if snap.minds_before.get(char_id) is None or snap.minds_before[char_id].model_dump() != value
    }
    return label, True


def _minds_by_seq(session_id: str) -> dict[int, dict]:
    """Mirrors replay.py's turn grouping to recover the merged minds map per turn: TurnSnapshot
    only keeps minds_before, and merge_minds returns the full map, not the delta this needs."""
    result: dict[int, dict] = {}
    group: list[Event] | None = None

    def close(group_events: list[Event]) -> None:
        narrator_event = next((e for e in group_events[1:] if e.kind == "narrator_turn"), None)
        if narrator_event is None:
            return
        minds_events = [e for e in group_events[1:] if e.kind == "minds"]
        if minds_events:
            entries = minds_events[-1].payload.get("entries")
            if isinstance(entries, dict):
                result[narrator_event.seq] = entries

    for event in read_events(session_id):
        if event.kind == "compact":
            if group is not None:
                close(group)
                group = None
            continue
        if event.kind in ("player_turn", "meta_player_turn"):
            if group is not None:
                close(group)
            group = [event] if event.kind == "player_turn" else None
            continue
        if group is None:
            continue
        group.append(event)
    if group is not None:
        close(group)
    return result


def _envelope(
    task: str,
    replay: SessionReplay,
    snap: TurnSnapshot,
    split: str,
    messages: list,
    engine_label: dict,
    applied: bool,
) -> dict:
    return {
        "task": task,
        "locale": replay.locale,
        "scenario_id": replay.scenario.id,
        "session_id": replay.session_id,
        "turn": snap.turn,
        "split": split,
        "messages": [message.model_dump() for message in messages],
        "engine_label": engine_label,
        "applied": applied,
    }


def _write_line(handle: TextIO, line: dict) -> None:
    handle.write(json.dumps(line, ensure_ascii=False))
    handle.write("\n")


def export_dataset(out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    counters = {
        "sessions": 0,
        "turns": 0,
        **{task: 0 for task in TASKS},
        "skipped_scenario": 0,
        "skipped_inexact": 0,
    }

    handles = {task: open(out_dir / f"{task}.jsonl", "w", encoding="utf-8") for task in TASKS}
    try:
        for summary in list_sessions():
            try:
                replay = replay_session(summary.id)
            except (ScenarioNotFound, SessionNotFound):
                counters["skipped_scenario"] += 1
                continue

            counters["sessions"] += 1
            minds_by_seq = _minds_by_seq(summary.id)
            split = split_for(summary.id)

            for snap in replay.turns:
                if not snap.exact:
                    counters["skipped_inexact"] += 1
                    continue

                counters["turns"] += 1

                judge_messages = build_judge_messages(
                    replay.scenario, snap.hud_after_tags, snap.message, snap.narrator_text, snap.touched_ids
                )
                judge_label, judge_applied = _judge_engine_label(snap)
                _write_line(
                    handles["judge"],
                    _envelope("judge", replay, snap, split, judge_messages, judge_label, judge_applied),
                )
                counters["judge"] += 1

                window = events_to_messages(
                    snap.history_before[-(DIRECTOR_WINDOW_TURNS * 2) :], replay.locale
                )
                director_messages = build_director_messages(
                    replay.scenario, snap.hud_start, snap.cast_before, snap.message, window
                )
                director_label, director_applied = _director_engine_label(snap)
                _write_line(
                    handles["director"],
                    _envelope(
                        "director", replay, snap, split, director_messages, director_label, director_applied
                    ),
                )
                counters["director"] += 1

                minds_messages = build_minds_messages(
                    replay.scenario, snap.cast_after, snap.minds_before, snap.message, snap.narrator_text
                )
                minds_label, minds_applied = _minds_engine_label(snap, minds_by_seq)
                _write_line(
                    handles["minds"],
                    _envelope("minds", replay, snap, split, minds_messages, minds_label, minds_applied),
                )
                counters["minds"] += 1
    finally:
        for handle in handles.values():
            handle.close()

    print(
        "sessions={sessions} turns={turns} judge={judge} director={director} minds={minds} "
        "skipped_scenario={skipped_scenario} skipped_inexact={skipped_inexact}".format(**counters)
    )
    return counters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="app.dataset")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    if args.command == "export":
        export_dataset(Path(args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
