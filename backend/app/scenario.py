from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from app.hud import validate_time, validate_weather
from app.observability import emit


class ScenarioError(Exception):
    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"{path}: {reason}")


class CharacterMind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feeling: str
    goal: str
    opinion_of_player: str | None = None
    secret_plan: str | None = None


class Character(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: str
    appearance: str
    personality: str
    voice: str
    mind: CharacterMind
    sprite: str | None = None


class HudDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str
    time: str = "08:00"
    weather: str = "clear"

    @field_validator("time")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        return validate_time(value)

    @field_validator("weather")
    @classmethod
    def _validate_weather(cls, value: str) -> str:
        return validate_weather(value)


class StartConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    prologue: str
    opening_scene: str
    play_guide: str | None = None
    suggestions: list[str] = []
    hud: HudDefaults
    characters: list[str] | None = None


class ScenarioMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    tagline: str | None = None
    description: str | None = None
    locale: Literal["en", "pt-br"] = "pt-br"
    tags: list[str] = []
    default_start: str = "default"


class LoadedScenario(BaseModel):
    id: str
    meta: ScenarioMeta
    world: str
    starts: dict[str, StartConfig]
    characters: dict[str, Character]

    def start(self, start_id: str | None = None) -> StartConfig:
        chosen = start_id or self.meta.default_start
        try:
            return self.starts[chosen]
        except KeyError:
            raise ScenarioError(Path(self.id), f"start '{chosen}' not found") from None


def scenarios_dir() -> Path:
    import os

    env_dir = os.environ.get("OOC_SCENARIOS_DIR")
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[2] / "scenarios"


def _load_yaml(path: Path, model: type[BaseModel]) -> BaseModel:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ScenarioError(path, "file not found") from None
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ScenarioError(path, f"invalid yaml: {exc}") from exc
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ScenarioError(path, str(exc)) from exc


def _load_world(scenario_path: Path) -> str:
    world_path = scenario_path / "world.md"
    if not world_path.exists():
        raise ScenarioError(world_path, "world.md is missing")
    text = world_path.read_text(encoding="utf-8")
    if not text.strip():
        raise ScenarioError(world_path, "world.md is empty")
    return text


def _load_starts(scenario_path: Path) -> dict[str, StartConfig]:
    starts_dir = scenario_path / "starts"
    if not starts_dir.is_dir():
        raise ScenarioError(starts_dir, "starts/ directory is missing")
    starts: dict[str, StartConfig] = {}
    for start_path in sorted(starts_dir.glob("*.yaml")):
        start_id = start_path.stem
        try:
            raw = start_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ScenarioError(start_path, "file not found") from None
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ScenarioError(start_path, f"invalid yaml: {exc}") from exc
        if not isinstance(data, dict):
            raise ScenarioError(start_path, "expected a mapping")
        data = {**data, "id": start_id}
        try:
            starts[start_id] = StartConfig.model_validate(data)
        except ValidationError as exc:
            raise ScenarioError(start_path, str(exc)) from exc
    if not starts:
        raise ScenarioError(starts_dir, "no start files found")
    return starts


def _load_characters(scenario_path: Path) -> dict[str, Character]:
    characters_dir = scenario_path / "characters"
    if not characters_dir.is_dir():
        raise ScenarioError(characters_dir, "characters/ directory is missing")
    characters: dict[str, Character] = {}
    for char_path in sorted(characters_dir.glob("*.yaml")):
        char_id = char_path.stem
        character = _load_yaml(char_path, Character)
        characters[char_id] = character
    if not characters:
        raise ScenarioError(characters_dir, "no character files found")
    return characters


def _confine_scenario_path(scenario_id: str) -> Path:
    root = scenarios_dir()
    if not scenario_id or scenario_id.startswith(".") or any(
        sep in scenario_id for sep in ("/", "\\", "\0")
    ):
        raise ScenarioError(root / str(scenario_id), "scenario id outside the scenarios root")
    scenario_path = (root / scenario_id).resolve()
    if root.resolve() not in scenario_path.parents:
        raise ScenarioError(scenario_path, "scenario id outside the scenarios root")
    return scenario_path


def load_scenario(scenario_id: str) -> LoadedScenario:
    scenario_path = _confine_scenario_path(scenario_id)
    meta_path = scenario_path / "scenario.yaml"
    if not meta_path.exists():
        raise ScenarioError(meta_path, "scenario.yaml is missing")
    meta = _load_yaml(meta_path, ScenarioMeta)

    world = _load_world(scenario_path)
    starts = _load_starts(scenario_path)
    characters = _load_characters(scenario_path)

    for start in starts.values():
        if start.characters is not None:
            unknown = [char_id for char_id in start.characters if char_id not in characters]
            if unknown:
                raise ScenarioError(
                    scenario_path / "starts" / f"{start.id}.yaml",
                    f"unknown character ids: {unknown}",
                )

    if meta.default_start not in starts:
        raise ScenarioError(
            meta_path,
            f"default_start '{meta.default_start}' not found; known starts: {sorted(starts)}",
        )

    return LoadedScenario(
        id=scenario_id,
        meta=meta,
        world=world,
        starts=starts,
        characters=characters,
    )


def list_scenarios() -> list[LoadedScenario]:
    root = scenarios_dir()
    if not root.is_dir():
        return []

    scenarios: list[LoadedScenario] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "scenario.yaml").exists():
            continue
        try:
            scenarios.append(load_scenario(entry.name))
        except ScenarioError as exc:
            emit("scenario_invalid", path=str(exc.path), error=exc.reason)

    scenarios.sort(key=lambda scenario: scenario.meta.name.casefold())
    return scenarios
