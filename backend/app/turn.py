from __future__ import annotations

import time
from collections.abc import AsyncIterator

from app.config import load_config
from app.hud import advance
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
from app.observability import emit
from app.prompt import MASTER_PROMPT_VERSION, build_master_prompt
from app.scenario import Character, LoadedScenario, StartConfig, load_scenario
from app.sessions import ScenarioNotFound, append_events, get_session_row, read_events
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


async def run_turn(session_id: str, message: str) -> AsyncIterator[dict]:
    config = load_config()
    role = config.models["narrator"]
    provider = OpenAICompatProvider(config.providers[role.provider])

    messages = build_context(session_id, message)
    hud = get_session_row(session_id).hud

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
