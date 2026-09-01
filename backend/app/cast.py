from __future__ import annotations

from pydantic import BaseModel

from app.scenario import LoadedScenario, StartConfig

CAST_EVENT_KIND = "cast"
MAX_CAST_IN_SCENE = 6


class CastMember(BaseModel):
    id: str
    name: str


def seed_cast_ids(scenario: LoadedScenario, start: StartConfig) -> list[str]:
    """Mirrors turn.py's _characters_in_scene: same seed, same order."""
    if start.characters is None:
        return list(scenario.characters)
    return list(start.characters)


def resolve_cast(scenario: LoadedScenario, ids: list[str]) -> list[CastMember]:
    """Ignores ids no longer present in the scenario; order is preserved."""
    members: list[CastMember] = []
    for char_id in ids:
        character = scenario.characters.get(char_id)
        if character is None:
            continue
        members.append(CastMember(id=char_id, name=character.name))
    return members


def validate_cast_ids(scenario: LoadedScenario, ids: object) -> tuple[list[str] | None, str | None]:
    """Deterministic judge for an LLM-proposed cast. Order of checks: shape -> ids -> cap."""
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        return None, "not_a_list"

    deduped: list[str] = []
    for char_id in ids:
        if char_id not in deduped:
            deduped.append(char_id)

    unknown = [char_id for char_id in deduped if char_id not in scenario.characters]
    if unknown:
        return None, "unknown_ids"

    if len(deduped) > MAX_CAST_IN_SCENE:
        return None, "over_cap"

    return deduped, None


def cast_event(ids: list[str], source: str) -> tuple[str, dict]:
    return CAST_EVENT_KIND, {"ids": ids, "source": source}
