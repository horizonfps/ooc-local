from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError

from app import scenario as scenario_module
from app.config import load_config
from app.observability import emit
from app.scenario import (
    Character,
    CommandDef,
    LoreEntry,
    ScenarioError,
    ScenarioMeta,
    StartConfig,
    StatDef,
)

router = APIRouter()

_ID_RE = re.compile(r"^[a-z0-9-]+$")


class ScenarioDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: str
    meta: ScenarioMeta
    world: str
    starts: dict[str, StartConfig]
    characters: dict[str, Character]
    stats: list[StatDef] = []
    lorebook: dict[str, LoreEntry] = {}
    commands: list[CommandDef] = []


class ScenarioDocumentWrite(ScenarioDocument):
    model_config = ConfigDict(extra="forbid")

    # Required on write: a client that omits them would otherwise wipe the files.
    stats: list[StatDef]
    lorebook: dict[str, LoreEntry]
    commands: list[CommandDef]
    force: bool = False


class ScenarioDocumentInvalid(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        summary = f"{len(errors)} erro(s): " + "; ".join(errors)
        super().__init__(summary)


class ScenarioDocumentConflict(Exception):
    def __init__(self, client_revision: str, disk_revision: str) -> None:
        self.client_revision = client_revision
        self.disk_revision = disk_revision
        super().__init__("revision conflict")


class ScenarioDocumentWriteFailed(Exception):
    def __init__(self, path: Path, error: str) -> None:
        self.path = path
        self.error = error
        super().__init__(f"{path}: {error}")


def _load_meta(scenario_dir: Path) -> ScenarioMeta:
    meta_path = scenario_dir / "scenario.yaml"
    result = scenario_module._load_yaml(meta_path, ScenarioMeta)
    assert isinstance(result, ScenarioMeta)
    return result


def _load_world(scenario_dir: Path) -> str:
    world_path = scenario_dir / "world.md"
    if not world_path.exists():
        return ""
    return world_path.read_text(encoding="utf-8")


def _load_dir(scenario_dir: Path, subdir: str, model: type[BaseModel], inject_id: bool) -> dict[str, BaseModel]:
    dir_path = scenario_dir / subdir
    result: dict[str, BaseModel] = {}
    if not dir_path.is_dir():
        return result
    seen_stems: set[str] = set()
    for file_path in sorted([*dir_path.glob("*.yaml"), *dir_path.glob("*.yml")]):
        stem = file_path.stem
        if stem in seen_stems:
            raise ScenarioError(dir_path, f"duplicate id '{stem}' in .yaml and .yml")
        seen_stems.add(stem)
        try:
            raw = file_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise ScenarioError(file_path, "file not found") from None
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ScenarioError(file_path, f"invalid yaml: {exc}") from exc
        if not isinstance(data, dict):
            raise ScenarioError(file_path, "expected a mapping")
        if inject_id:
            data = {**data, "id": stem}
        try:
            result[stem] = model.model_validate(data)
        except ValidationError as exc:
            raise ScenarioError(file_path, scenario_module._summarize(exc), details=str(exc)) from exc
    return result


def _load_list(scenario_dir: Path, filename: str, model: type[BaseModel]) -> list[BaseModel]:
    """Missing file or empty (null) YAML document is a valid empty list, never an error."""
    path = scenario_dir / filename
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
            raise ScenarioError(path, scenario_module._summarize(exc), details=str(exc)) from exc
    return items


def read_document(scenario_id: str) -> ScenarioDocument:
    scenario_dir = scenario_module.scenario_path(scenario_id)
    meta = _load_meta(scenario_dir)
    world = _load_world(scenario_dir)
    starts = _load_dir(scenario_dir, "starts", StartConfig, inject_id=True)
    characters = _load_dir(scenario_dir, "characters", Character, inject_id=False)
    stats = _load_list(scenario_dir, "stats.yaml", StatDef)
    lorebook = _load_dir(scenario_dir, "lorebook", LoreEntry, inject_id=False)
    commands = _load_list(scenario_dir, "commands.yaml", CommandDef)
    revision = compute_revision(scenario_id)
    return ScenarioDocument(
        revision=revision,
        meta=meta,
        world=world,
        starts=starts,
        characters=characters,
        stats=stats,
        lorebook=lorebook,
        commands=commands,
    )


def compute_revision(scenario_id: str) -> str:
    """sha256 over sorted (relpath, bytes) of every scenario file outside media/."""
    scenario_dir = scenario_module.scenario_path(scenario_id)
    files: list[Path] = []
    meta_path = scenario_dir / "scenario.yaml"
    if meta_path.exists():
        files.append(meta_path)
    world_path = scenario_dir / "world.md"
    if world_path.exists():
        files.append(world_path)
    for subdir in ("starts", "characters"):
        dir_path = scenario_dir / subdir
        if dir_path.is_dir():
            files.extend([*dir_path.glob("*.yaml"), *dir_path.glob("*.yml")])
    stats_path = scenario_dir / "stats.yaml"
    if stats_path.exists():
        files.append(stats_path)
    commands_path = scenario_dir / "commands.yaml"
    if commands_path.exists():
        files.append(commands_path)
    lorebook_dir = scenario_dir / "lorebook"
    if lorebook_dir.is_dir():
        files.extend([*lorebook_dir.glob("*.yaml"), *lorebook_dir.glob("*.yml")])

    def relkey(path: Path) -> str:
        return path.relative_to(scenario_dir).as_posix()

    files.sort(key=relkey)

    digest = hashlib.sha256()
    for path in files:
        relpath = relkey(path)
        data = path.read_bytes()
        digest.update(relpath.encode())
        digest.update(b"\0")
        digest.update(str(len(data)).encode())
        digest.update(b"\0")
        digest.update(data)
    return digest.hexdigest()[:16]


def _validate_document(doc: ScenarioDocument) -> None:
    errors: list[str] = []
    if not doc.starts:
        errors.append("at least one start is required")
    if doc.meta.default_start not in doc.starts:
        errors.append(f"default_start '{doc.meta.default_start}' not found in starts")
    for start_id, start in doc.starts.items():
        if not _ID_RE.match(start_id):
            errors.append(f"invalid start id '{start_id}', expected [a-z0-9-]+")
        if start.characters:
            unknown = [char_id for char_id in start.characters if char_id not in doc.characters]
            if unknown:
                errors.append(f"start '{start_id}' references unknown character ids: {unknown}")
    for char_id in doc.characters:
        if not _ID_RE.match(char_id):
            errors.append(f"invalid character id '{char_id}', expected [a-z0-9-]+")
    for lore_id in doc.lorebook:
        if not _ID_RE.match(lore_id):
            errors.append(f"invalid lorebook id '{lore_id}', expected [a-z0-9-]+")
    seen_stat_ids: set[str] = set()
    for stat in doc.stats:
        if stat.id in seen_stat_ids:
            errors.append(f"duplicate stat id '{stat.id}'")
        seen_stat_ids.add(stat.id)
    seen_command_names: set[str] = set()
    for command in doc.commands:
        if command.name in seen_command_names:
            errors.append(f"duplicate command name '{command.name}'")
        seen_command_names.add(command.name)
    if errors:
        raise ScenarioDocumentInvalid(errors)


def _dump_yaml(data: dict | list) -> bytes:
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    if not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _serialize_meta(meta: ScenarioMeta) -> bytes:
    data: dict = {"name": meta.name}
    if meta.tagline is not None:
        data["tagline"] = meta.tagline
    if meta.description is not None:
        data["description"] = meta.description
    data["locale"] = meta.locale
    data["world_mode"] = meta.world_mode
    data["tags"] = meta.tags
    data["default_start"] = meta.default_start
    return _dump_yaml(data)


def _serialize_world(world: str) -> bytes:
    text = world.replace("\r\n", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text.encode("utf-8")


def _serialize_start(start: StartConfig) -> bytes:
    data: dict = {
        "name": start.name,
        "prologue": start.prologue,
        "opening_scene": start.opening_scene,
    }
    if start.conflict is not None:
        data["conflict"] = start.conflict
    if start.mission is not None:
        data["mission"] = start.mission
    if start.play_guide is not None:
        data["play_guide"] = start.play_guide
    data["suggestions"] = start.suggestions
    data["hud"] = {
        "location": start.hud.location,
        "time": start.hud.time,
        "weather": start.hud.weather,
    }
    if start.characters is not None:
        data["characters"] = start.characters
    return _dump_yaml(data)


def _serialize_character(character: Character) -> bytes:
    data: dict = {
        "name": character.name,
        "role": character.role,
        "appearance": character.appearance,
        "personality": character.personality,
        "voice": character.voice,
    }
    mind: dict = {
        "feeling": character.mind.feeling,
        "goal": character.mind.goal,
    }
    if character.mind.opinion_of_player is not None:
        mind["opinion_of_player"] = character.mind.opinion_of_player
    if character.mind.secret_plan is not None:
        mind["secret_plan"] = character.mind.secret_plan
    data["mind"] = mind
    if character.sprite is not None:
        data["sprite"] = character.sprite
    if character.power_tier is not None:
        data["power_tier"] = character.power_tier
    data["emotions"] = character.emotions
    return _dump_yaml(data)


def _serialize_stat_def(stat: StatDef) -> dict:
    data: dict = {"id": stat.id, "name": stat.name}
    if stat.icon is not None:
        data["icon"] = stat.icon
    if stat.color is not None:
        data["color"] = stat.color
    data["min"] = stat.min
    data["max"] = stat.max
    data["default"] = stat.default
    if stat.description is not None:
        data["description"] = stat.description
    if stat.levels:
        data["levels"] = [{"from": level.from_, "text": level.text} for level in stat.levels]
    return data


def _serialize_stats(stats: list[StatDef]) -> bytes:
    return _dump_yaml([_serialize_stat_def(stat) for stat in stats])


def _serialize_lore_entry(entry: LoreEntry) -> bytes:
    data: dict = {"title": entry.title}
    if entry.keywords:
        data["keywords"] = entry.keywords
    data["body"] = entry.body
    data["scope"] = entry.scope
    data["priority"] = entry.priority
    data["enabled"] = entry.enabled
    return _dump_yaml(data)


def _serialize_command_def(command: CommandDef) -> dict:
    return {"name": command.name, "description": command.description, "prompt": command.prompt}


def _serialize_commands(commands: list[CommandDef]) -> bytes:
    return _dump_yaml([_serialize_command_def(command) for command in commands])


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".{path.name}.tmp-{uuid.uuid4().hex}"
    tmp_path.write_bytes(content)
    os.replace(tmp_path, path)


def _prune_dir(dir_path: Path, keep_ids: set[str]) -> int:
    """Remove ids no longer in the payload and stray non-.yaml duplicates of kept ids."""
    if not dir_path.is_dir():
        return 0
    deleted = 0
    for file_path in [*dir_path.glob("*.yaml"), *dir_path.glob("*.yml")]:
        if file_path.stem not in keep_ids or file_path.suffix != ".yaml":
            file_path.unlink()
            deleted += 1
    return deleted


def write_document(scenario_id: str, doc: ScenarioDocument, *, force: bool) -> str:
    _validate_document(doc)

    disk_revision = compute_revision(scenario_id)
    if doc.revision != disk_revision and not force:
        emit(
            "builder_doc_conflict",
            scenario_id=scenario_id,
            client_revision=doc.revision,
            disk_revision=disk_revision,
        )
        raise ScenarioDocumentConflict(client_revision=doc.revision, disk_revision=disk_revision)

    scenario_dir = scenario_module.scenario_path(scenario_id)

    targets: dict[Path, bytes] = {
        scenario_dir / "scenario.yaml": _serialize_meta(doc.meta),
        scenario_dir / "world.md": _serialize_world(doc.world),
    }
    for start_id, start in doc.starts.items():
        targets[scenario_dir / "starts" / f"{start_id}.yaml"] = _serialize_start(start)
    for char_id, character in doc.characters.items():
        targets[scenario_dir / "characters" / f"{char_id}.yaml"] = _serialize_character(character)
    if doc.stats:
        targets[scenario_dir / "stats.yaml"] = _serialize_stats(doc.stats)
    if doc.commands:
        targets[scenario_dir / "commands.yaml"] = _serialize_commands(doc.commands)
    for lore_id, entry in doc.lorebook.items():
        targets[scenario_dir / "lorebook" / f"{lore_id}.yaml"] = _serialize_lore_entry(entry)

    try:
        files_written = 0
        for path, content in targets.items():
            if path.exists() and path.read_bytes() == content:
                continue
            _atomic_write(path, content)
            files_written += 1

        files_deleted = _prune_dir(scenario_dir / "starts", set(doc.starts))
        files_deleted += _prune_dir(scenario_dir / "characters", set(doc.characters))
        files_deleted += _prune_dir(scenario_dir / "lorebook", set(doc.lorebook))

        stats_path = scenario_dir / "stats.yaml"
        if not doc.stats and stats_path.exists():
            stats_path.unlink()
            files_deleted += 1
        commands_path = scenario_dir / "commands.yaml"
        if not doc.commands and commands_path.exists():
            commands_path.unlink()
            files_deleted += 1
    except OSError as exc:
        path = Path(exc.filename) if exc.filename else scenario_dir
        emit("builder_doc_write_failed", scenario_id=scenario_id, path=str(path), error=str(exc))
        raise ScenarioDocumentWriteFailed(path, str(exc)) from exc

    new_revision = compute_revision(scenario_id)
    emit(
        "builder_doc_saved",
        scenario_id=scenario_id,
        files_written=files_written,
        files_deleted=files_deleted,
        forced=force,
        revision=new_revision,
    )
    return new_revision


@router.get("/api/builder/scenarios/{scenario_id}", response_model=ScenarioDocument)
async def get_builder_document_route(scenario_id: str) -> ScenarioDocument:
    try:
        scenario_dir = scenario_module.scenario_path(scenario_id)
    except ScenarioError:
        raise HTTPException(status_code=422, detail="invalid folder") from None
    if not scenario_dir.is_dir() or not (scenario_dir / "scenario.yaml").exists():
        raise HTTPException(status_code=404, detail="scenario not found")

    try:
        document = read_document(scenario_id)
    except ScenarioError as exc:
        reason = exc.reason.replace("\n", " ")[:300]
        emit("builder_doc_invalid", scenario_id=scenario_id, path=str(exc.path), reason=reason)
        raise HTTPException(status_code=422, detail=f"{exc.path}: {reason}") from None

    emit(
        "builder_doc_read",
        scenario_id=scenario_id,
        starts=len(document.starts),
        characters=len(document.characters),
        stats=len(document.stats),
        lore=len(document.lorebook),
        commands=len(document.commands),
        revision=document.revision,
    )
    return document


@router.put("/api/builder/scenarios/{scenario_id}")
async def put_builder_document_route(scenario_id: str, req: ScenarioDocumentWrite) -> dict[str, str]:
    config = load_config()
    if not config.flag("builder"):
        emit("builder_rejected", scenario_id=scenario_id, reason="builder disabled by flag")
        raise HTTPException(status_code=503, detail="builder disabled by flag")

    try:
        scenario_dir = scenario_module.scenario_path(scenario_id)
    except ScenarioError:
        raise HTTPException(status_code=422, detail="invalid folder") from None
    if not scenario_dir.is_dir() or not (scenario_dir / "scenario.yaml").exists():
        raise HTTPException(status_code=404, detail="scenario not found")

    doc = ScenarioDocument(
        revision=req.revision,
        meta=req.meta,
        world=req.world,
        starts=req.starts,
        characters=req.characters,
        stats=req.stats,
        lorebook=req.lorebook,
        commands=req.commands,
    )

    try:
        revision = write_document(scenario_id, doc, force=req.force)
    except ScenarioDocumentInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except ScenarioDocumentConflict:
        raise HTTPException(status_code=409, detail="revision conflict") from None
    except ScenarioDocumentWriteFailed:
        raise HTTPException(status_code=500, detail="write failed") from None

    return {"revision": revision}
