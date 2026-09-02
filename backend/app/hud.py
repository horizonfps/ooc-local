from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

if TYPE_CHECKING:
    from app.scenario import LoadedScenario, StartConfig, StatDef

WEATHER_CODES = ("clear", "cloudy", "rain", "storm", "snow", "fog", "night")

TURN_MINUTES = 2
LOCATION_MAX_CHARS = 60

_WHITESPACE_RE = re.compile(r"\s+")

TIME_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
_TIME_RE = re.compile(TIME_PATTERN)


def validate_time(value: str) -> str:
    if not _TIME_RE.match(value):
        raise ValueError(f"invalid time '{value}', expected HH:MM 24h")
    return value


def validate_weather(value: str) -> str:
    if value not in WEATHER_CODES:
        raise ValueError(f"invalid weather '{value}', expected one of {WEATHER_CODES}")
    return value


class DynamicStat(BaseModel):
    name: str
    value: int
    min: int = 0
    max: int


class StatView(BaseModel):
    id: str
    name: str
    icon: str | None
    color: str | None
    value: int
    min: int
    max: int
    level: str | None


class HudState(BaseModel):
    turn: int = 0
    location: str
    time: str
    weather: str
    stats: dict[str, int] = {}
    dynamic_stats: dict[str, DynamicStat] = {}

    @field_validator("time")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        return validate_time(value)

    @field_validator("weather")
    @classmethod
    def _validate_weather(cls, value: str) -> str:
        return validate_weather(value)


def stat_views(scenario: "LoadedScenario", hud: HudState) -> list[StatView]:
    """One StatView per declared stat, in scenario order, followed by dynamic stats
    in hud.dynamic_stats insertion order."""
    views: list[StatView] = []
    for stat in scenario.stats:
        value = hud.stats.get(stat.id, stat.default)
        level_text: str | None = None
        for level in stat.levels:
            if level.from_ <= value:
                level_text = level.text
            else:
                break
        views.append(
            StatView(
                id=stat.id,
                name=stat.name,
                icon=stat.icon,
                color=stat.color,
                value=value,
                min=stat.min,
                max=stat.max,
                level=level_text,
            )
        )
    for stat_id, dynamic in hud.dynamic_stats.items():
        views.append(
            StatView(
                id=stat_id,
                name=dynamic.name,
                icon=None,
                color=None,
                value=dynamic.value,
                min=dynamic.min,
                max=dynamic.max,
                level=None,
            )
        )
    return views


def hud_from_start(start: "StartConfig") -> HudState:
    return HudState(
        turn=0,
        location=start.hud.location,
        time=start.hud.time,
        weather=start.hud.weather,
    )


def advance(hud: HudState) -> HudState:
    """Deterministic engine clock: turn +1, in-world time +TURN_MINUTES, wraps at midnight."""
    hours, minutes = (int(part) for part in hud.time.split(":"))
    total = (hours * 60 + minutes + TURN_MINUTES) % (24 * 60)
    new_time = f"{total // 60:02d}:{total % 60:02d}"
    return hud.model_copy(update={"turn": hud.turn + 1, "time": new_time})


def apply_location(hud: HudState, raw: str) -> HudState:
    """Engine-owned HUD move: normalizes and applies a narrator location tag."""
    normalized = _WHITESPACE_RE.sub(" ", raw.strip())
    if not normalized:
        return hud
    if len(normalized) > LOCATION_MAX_CHARS:
        truncated = normalized[:LOCATION_MAX_CHARS]
        cut = truncated.rfind(" ")
        normalized = truncated[:cut] if cut > 0 else truncated
    if normalized == hud.location:
        return hud
    return hud.model_copy(update={"location": normalized})


STAT_EVENT_KIND = "stat"


def stat_ids(hud: HudState, stats: list["StatDef"]) -> set[str]:
    """Union of declared stat ids and dynamic stat ids: the source of truth for "does this id exist?"."""
    return {stat.id for stat in stats} | set(hud.dynamic_stats)


def ensure_stats(hud: HudState, stats: list["StatDef"]) -> HudState:
    """Fills in missing declared stat keys with their default and re-clamps values left outside an
    edited range; never removes a key the author dropped."""
    updated = dict(hud.stats)
    changed = False
    for stat in stats:
        current = updated.get(stat.id)
        if current is None:
            updated[stat.id] = stat.default
            changed = True
            continue
        clamped = min(max(current, stat.min), stat.max)
        if clamped != current:
            updated[stat.id] = clamped
            changed = True
    if not changed:
        return hud
    return hud.model_copy(update={"stats": updated})


def apply_stat(
    hud: HudState, stats: list["StatDef"], stat_id: str, delta: int
) -> tuple[HudState, tuple[int, int] | None]:
    """Clamped delta on a declared or dynamic stat. Unknown id or a clamp that didn't
    move returns (hud, None); otherwise (hud novo, (delta efetivo, valor novo))."""
    if stat_id not in stat_ids(hud, stats):
        return hud, None

    declared = next((stat for stat in stats if stat.id == stat_id), None)
    if declared is not None:
        current = hud.stats.get(stat_id, declared.default)
        new_value = min(max(current + delta, declared.min), declared.max)
        if new_value == current:
            return hud, None
        new_hud = hud.model_copy(update={"stats": {**hud.stats, stat_id: new_value}})
        return new_hud, (new_value - current, new_value)

    dynamic = hud.dynamic_stats[stat_id]
    current = dynamic.value
    new_value = min(max(current + delta, dynamic.min), dynamic.max)
    if new_value == current:
        return hud, None
    new_dynamic = dynamic.model_copy(update={"value": new_value})
    new_hud = hud.model_copy(update={"dynamic_stats": {**hud.dynamic_stats, stat_id: new_dynamic}})
    return new_hud, (new_value - current, new_value)


def stat_event(stat_id: str, delta: int, value: int, source: str) -> tuple[str, dict]:
    return STAT_EVENT_KIND, {"id": stat_id, "delta": delta, "value": value, "source": source}
