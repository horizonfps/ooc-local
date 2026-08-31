from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.scenario import StartConfig

WEATHER_CODES = ("clear", "cloudy", "rain", "storm", "snow", "fog", "night")

TURN_MINUTES = 2


class HudState(BaseModel):
    turn: int = 0
    location: str
    time: str
    weather: str


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
