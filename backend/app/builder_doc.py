from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError

from app import scenario as scenario_module
from app.observability import emit
from app.scenario import Character, ScenarioError, ScenarioMeta, StartConfig

router = APIRouter()


class ScenarioDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: str
    meta: ScenarioMeta
    world: str
    starts: dict[str, StartConfig]
    characters: dict[str, Character]


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


def read_document(scenario_id: str) -> ScenarioDocument:
    scenario_dir = scenario_module.scenario_path(scenario_id)
    meta = _load_meta(scenario_dir)
    world = _load_world(scenario_dir)
    starts = _load_dir(scenario_dir, "starts", StartConfig, inject_id=True)
    characters = _load_dir(scenario_dir, "characters", Character, inject_id=False)
    revision = compute_revision(scenario_id)
    return ScenarioDocument(
        revision=revision,
        meta=meta,
        world=world,
        starts=starts,
        characters=characters,
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
        revision=document.revision,
    )
    return document
