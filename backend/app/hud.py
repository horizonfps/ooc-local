from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.scenario import StartConfig

WEATHER_CODES = ("clear", "cloudy", "rain", "storm", "snow", "fog", "night")


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
