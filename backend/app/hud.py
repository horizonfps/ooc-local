from __future__ import annotations

import re
from typing import TYPE_CHECKING

from pydantic import BaseModel, field_validator

if TYPE_CHECKING:
    from app.scenario import StartConfig

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


class HudState(BaseModel):
    turn: int = 0
    location: str
    time: str
    weather: str

    @field_validator("time")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        return validate_time(value)

    @field_validator("weather")
    @classmethod
    def _validate_weather(cls, value: str) -> str:
        return validate_weather(value)


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
