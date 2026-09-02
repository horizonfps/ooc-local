from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.hud import validate_time, validate_weather
from app.observability import emit


class ScenarioError(Exception):
    def __init__(self, path: Path, reason: str, details: str | None = None) -> None:
        self.path = path
        self.reason = reason
        self.details = details
        super().__init__(f"{path}: {reason}")


def _summarize(exc: ValidationError) -> str:
    parts = [f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}" for error in exc.errors()]
    summary = f"{len(parts)} erro(s): " + "; ".join(parts)
    summary = summary.replace("\n", " ")
    if len(summary) > 300:
        summary = summary[:300]
    return summary


class CharacterMind(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feeling: str
    goal: str
    opinion_of_player: str | None = None
    secret_plan: str | None = None


_EMOTION_RE = re.compile(r"^[a-z0-9-]+$")


class Character(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: str
    appearance: str
    personality: str
    voice: str
    mind: CharacterMind
    sprite: str | None = None
    power_tier: int | None = Field(default=None, ge=1)
    emotions: list[str] = Field(default_factory=lambda: ["default"])

    @field_validator("emotions")
    @classmethod
    def _validate_emotions(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            item = item.strip()
            if not _EMOTION_RE.match(item):
                raise ValueError(f"invalid emotion '{item}', expected [a-z0-9-]+")
            if item not in normalized:
                normalized.append(item)
        if "default" in normalized:
            normalized.remove("default")
        normalized.insert(0, "default")
        if len(normalized) > 20:
            raise ValueError("too many emotions, expected at most 20")
        return normalized


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
    conflict: str | None = None
    mission: str | None = None
    play_guide: str | None = None
    suggestions: list[str] = []
    hud: HudDefaults
    characters: list[str] | None = None

    @field_validator("conflict", "mission")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


_STAT_ID_RE = re.compile(r"^[a-z0-9_-]+$")
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_COMMAND_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_LORE_ID_RE = re.compile(r"^[a-z0-9-]+$")


class StatLevel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: int = Field(validation_alias="from", serialization_alias="from")
    text: str


class StatDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    icon: str | None = None
    color: str | None = None
    min: int = 0
    max: int
    default: int
    description: str | None = None
    levels: list[StatLevel] = []

    @field_validator("id")
    @classmethod
    def _validate_id(cls, value: str) -> str:
        if not _STAT_ID_RE.match(value):
            raise ValueError(f"invalid stat id '{value}', expected [a-z0-9_-]+")
        return value

    @field_validator("icon")
    @classmethod
    def _validate_icon(cls, value: str | None) -> str | None:
        if value is not None and len(value) > 4:
            raise ValueError("icon must be at most 4 chars")
        return value

    @field_validator("color")
    @classmethod
    def _validate_color(cls, value: str | None) -> str | None:
        if value is not None and not _COLOR_RE.match(value):
            raise ValueError(f"invalid color '{value}', expected #RRGGBB")
        return value

    @model_validator(mode="after")
    def _validate_ranges(self) -> "StatDef":
        if self.max <= self.min:
            raise ValueError("max must be greater than min")
        if not (self.min <= self.default <= self.max):
            raise ValueError("default must be within [min, max]")
        previous_from: int | None = None
        for level in self.levels:
            if previous_from is not None and level.from_ <= previous_from:
                raise ValueError("levels 'from' must be strictly increasing")
            if not (self.min <= level.from_ <= self.max):
                raise ValueError("level 'from' must be within [min, max]")
            previous_from = level.from_
        return self


class LoreEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    keywords: list[str] = []
    body: str
    scope: Literal["keyword", "always"] = "keyword"
    priority: int = 0
    enabled: bool = True

    @model_validator(mode="after")
    def _validate_keywords(self) -> "LoreEntry":
        if self.scope == "keyword" and not self.keywords:
            raise ValueError("keywords must not be empty when scope is 'keyword'")
        return self


class CommandDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    prompt: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if not _COMMAND_NAME_RE.match(value):
            raise ValueError(f"invalid command name '{value}', expected [a-z0-9_-]+")
        return value


class CommandView(BaseModel):
    name: str
    description: str
    scope: Literal["scenario", "global"]


class ScenarioMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    tagline: str | None = None
    description: str | None = None
    locale: Literal["en", "pt-br"] = "pt-br"
    tags: list[str] = []
    default_start: str = "default"
    world_mode: Literal["guided", "custom"] = "guided"
    allow_dynamic_stats: bool = False


class LoadedScenario(BaseModel):
    id: str
    meta: ScenarioMeta
    world: str
    starts: dict[str, StartConfig]
    characters: dict[str, Character]
    stats: list[StatDef] = []
    lorebook: dict[str, LoreEntry] = {}
    commands: list[CommandDef] = []

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
        raise ScenarioError(path, _summarize(exc), details=str(exc)) from exc


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
    seen_stems: set[str] = set()
    for start_path in sorted([*starts_dir.glob("*.yaml"), *starts_dir.glob("*.yml")]):
        start_id = start_path.stem
        if start_id in seen_stems:
            raise ScenarioError(starts_dir, f"duplicate id '{start_id}' in .yaml and .yml")
        seen_stems.add(start_id)
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
            raise ScenarioError(start_path, _summarize(exc), details=str(exc)) from exc
    if not starts:
        raise ScenarioError(starts_dir, "no start files found")
    return starts


def _load_characters(scenario_path: Path) -> dict[str, Character]:
    characters_dir = scenario_path / "characters"
    if not characters_dir.is_dir():
        raise ScenarioError(characters_dir, "characters/ directory is missing")
    characters: dict[str, Character] = {}
    seen_stems: set[str] = set()
    for char_path in sorted([*characters_dir.glob("*.yaml"), *characters_dir.glob("*.yml")]):
        char_id = char_path.stem
        if char_id in seen_stems:
            raise ScenarioError(characters_dir, f"duplicate id '{char_id}' in .yaml and .yml")
        seen_stems.add(char_id)
        character = _load_yaml(char_path, Character)
        characters[char_id] = character
    if not characters:
        raise ScenarioError(characters_dir, "no character files found")
    return characters


def _load_list_file(path: Path, model: type[BaseModel]) -> list[BaseModel]:
    """Missing file or empty (null) YAML document is a valid empty list, never an error."""
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ScenarioError(path, f"invalid yaml: {exc}") from exc
    if data is None:
        return []
    if not isinstance(data, list):
        raise ScenarioError(path, "expected a list")
    items: list[BaseModel] = []
    for entry in data:
        try:
            items.append(model.model_validate(entry))
        except ValidationError as exc:
            raise ScenarioError(path, _summarize(exc), details=str(exc)) from exc
    return items


def _load_stats(scenario_path: Path) -> list[StatDef]:
    stats_path = scenario_path / "stats.yaml"
    stats = _load_list_file(stats_path, StatDef)
    seen: set[str] = set()
    for stat in stats:
        if stat.id in seen:
            raise ScenarioError(stats_path, f"duplicate stat id '{stat.id}'")
        seen.add(stat.id)
    return stats


def _load_commands(scenario_path: Path) -> list[CommandDef]:
    commands_path = scenario_path / "commands.yaml"
    commands = _load_list_file(commands_path, CommandDef)
    seen: set[str] = set()
    for command in commands:
        if command.name in seen:
            raise ScenarioError(commands_path, f"duplicate command name '{command.name}'")
        seen.add(command.name)
    return commands


def _load_lorebook(scenario_path: Path) -> dict[str, LoreEntry]:
    lorebook_dir = scenario_path / "lorebook"
    entries: dict[str, LoreEntry] = {}
    if not lorebook_dir.is_dir():
        return entries
    seen_stems: set[str] = set()
    for entry_path in sorted([*lorebook_dir.glob("*.yaml"), *lorebook_dir.glob("*.yml")]):
        stem = entry_path.stem
        if stem in seen_stems:
            raise ScenarioError(lorebook_dir, f"duplicate id '{stem}' in .yaml and .yml")
        seen_stems.add(stem)
        if not _LORE_ID_RE.match(stem):
            raise ScenarioError(entry_path, f"invalid lorebook id '{stem}', expected [a-z0-9-]+")
        entries[stem] = _load_yaml(entry_path, LoreEntry)
    return entries


def scenario_path(scenario_id: str) -> Path:
    """Scenario folder confined to scenarios_dir(); raises ScenarioError otherwise.
    Works for folders that do not exist yet."""
    root = scenarios_dir()
    if not scenario_id or scenario_id.startswith(".") or any(
        sep in scenario_id for sep in ("/", "\\", "\0")
    ):
        raise ScenarioError(root / str(scenario_id), "scenario id outside the scenarios root")
    resolved = (root / scenario_id).resolve()
    if root.resolve() not in resolved.parents:
        raise ScenarioError(resolved, "scenario id outside the scenarios root")
    return resolved


def load_scenario(scenario_id: str) -> LoadedScenario:
    scenario_dir = scenario_path(scenario_id)
    meta_path = scenario_dir / "scenario.yaml"
    if not meta_path.exists():
        raise ScenarioError(meta_path, "scenario.yaml is missing")
    meta = _load_yaml(meta_path, ScenarioMeta)

    world = _load_world(scenario_dir)
    starts = _load_starts(scenario_dir)
    characters = _load_characters(scenario_dir)
    stats = _load_stats(scenario_dir)
    lorebook = _load_lorebook(scenario_dir)
    commands = _load_commands(scenario_dir)

    for start in starts.values():
        if start.characters is not None:
            unknown = [char_id for char_id in start.characters if char_id not in characters]
            if unknown:
                raise ScenarioError(
                    scenario_dir / "starts" / f"{start.id}.yaml",
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
        stats=stats,
        lorebook=lorebook,
        commands=commands,
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
        except Exception as exc:  # noqa: BLE001 - listing must survive any single bad scenario
            error = str(exc).replace("\n", " ")[:300]
            emit(
                "scenario_invalid",
                path=str(entry),
                error=error,
                error_type=type(exc).__name__,
            )

    scenarios.sort(key=lambda scenario: scenario.meta.name.casefold())
    return scenarios
