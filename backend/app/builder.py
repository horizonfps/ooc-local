from __future__ import annotations

import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app import scenario as scenario_module
from app.observability import emit
from app.scenario import ScenarioError, ScenarioMeta

router = APIRouter(prefix="/api/builder")

FOLDER_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
COVER_NAMES = ("cover.png", "cover.jpg", "cover.webp")


class BuilderScenarioItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    name: str
    tagline: str | None = None
    locale: str = "pt-br"
    start_count: int = Field(0, alias="startCount")
    character_count: int = Field(0, alias="characterCount")
    has_cover: bool = Field(False, alias="hasCover")
    updated_at: str = Field(alias="updatedAt")
    status: Literal["ok", "invalid"] = "ok"
    reason: str | None = None


class CreateScenarioRequest(BaseModel):
    folder: str
    name: str
    locale: str


class DuplicateScenarioRequest(BaseModel):
    folder: str


def _iso_from_mtime(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _count_yaml_files(directory: Path) -> int:
    if not directory.is_dir():
        return 0
    return len([*directory.glob("*.yaml"), *directory.glob("*.yml")])


def _has_cover(scenario_dir: Path) -> bool:
    media_dir = scenario_dir / "media"
    return any((media_dir / name).exists() for name in COVER_NAMES)


def _latest_mtime(scenario_dir: Path) -> float:
    latest = scenario_dir.stat().st_mtime
    for path in scenario_dir.rglob("*"):
        if "media" in path.relative_to(scenario_dir).parts:
            continue
        if path.is_file():
            latest = max(latest, path.stat().st_mtime)
    return latest


def _scan_entry(scenario_dir: Path) -> BuilderScenarioItem:
    scenario_id = scenario_dir.name
    updated_at = _iso_from_mtime(_latest_mtime(scenario_dir))
    try:
        meta = scenario_module._load_yaml(scenario_dir / "scenario.yaml", ScenarioMeta)
    except ScenarioError as exc:
        emit("scenario_invalid", path=str(exc.path), error=exc.reason)
        return BuilderScenarioItem(
            id=scenario_id,
            name=scenario_id,
            updated_at=updated_at,
            status="invalid",
            reason=exc.reason,
        )
    assert isinstance(meta, ScenarioMeta)
    return BuilderScenarioItem(
        id=scenario_id,
        name=meta.name,
        tagline=meta.tagline,
        locale=meta.locale,
        start_count=_count_yaml_files(scenario_dir / "starts"),
        character_count=_count_yaml_files(scenario_dir / "characters"),
        has_cover=_has_cover(scenario_dir),
        updated_at=updated_at,
        status="ok",
    )


def scan_scenarios() -> list[BuilderScenarioItem]:
    root = scenario_module.scenarios_dir()
    if not root.is_dir():
        return []

    items: list[BuilderScenarioItem] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if not (entry / "scenario.yaml").exists():
            continue
        try:
            items.append(_scan_entry(entry))
        except Exception as exc:  # noqa: BLE001 - listing must survive any single bad scenario
            reason = str(exc).replace("\n", " ")[:300]
            emit("scenario_invalid", path=str(entry), error=reason, error_type=type(exc).__name__)
            items.append(
                BuilderScenarioItem(
                    id=entry.name,
                    name=entry.name,
                    updated_at=_iso_from_mtime(entry.stat().st_mtime),
                    status="invalid",
                    reason=reason,
                )
            )

    items.sort(key=lambda item: item.name.casefold())
    return items


def scan_one(scenario_id: str) -> BuilderScenarioItem:
    target = scenario_module.scenario_path(scenario_id)
    return _scan_entry(target)


def _write_skeleton(tmp_dir: Path, name: str, locale: str) -> None:
    tmp_dir.mkdir(parents=True)
    meta = {
        "name": name,
        "tagline": None,
        "description": None,
        "locale": locale,
        "world_mode": "guided",
        "tags": [],
        "default_start": "default",
    }
    (tmp_dir / "scenario.yaml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    (tmp_dir / "world.md").write_text("## Universe\n\n", encoding="utf-8")

    starts_dir = tmp_dir / "starts"
    starts_dir.mkdir()
    start = {
        "name": "default",
        "prologue": "",
        "opening_scene": "",
        "play_guide": None,
        "suggestions": [],
        "hud": {"location": "", "time": "08:00", "weather": "clear"},
        "characters": None,
    }
    (starts_dir / "default.yaml").write_text(
        yaml.safe_dump(start, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    (tmp_dir / "characters").mkdir()
    (tmp_dir / "media" / "sprites").mkdir(parents=True)
    (tmp_dir / "media" / "backgrounds").mkdir(parents=True)


def _resolve_target(folder: str) -> Path:
    if not FOLDER_RE.match(folder):
        raise HTTPException(status_code=422, detail="invalid folder")
    try:
        return scenario_module.scenario_path(folder)
    except ScenarioError:
        raise HTTPException(status_code=422, detail="invalid folder") from None


def _resolve_source(scenario_id: str) -> Path:
    try:
        source = scenario_module.scenario_path(scenario_id)
    except ScenarioError:
        raise HTTPException(status_code=422, detail="invalid folder") from None
    if not source.is_dir() or not (source / "scenario.yaml").exists():
        raise HTTPException(status_code=404, detail="scenario not found")
    return source


@router.get("/scenarios", response_model=list[BuilderScenarioItem])
async def list_builder_scenarios_route() -> list[BuilderScenarioItem]:
    return scan_scenarios()


@router.post("/scenarios", response_model=BuilderScenarioItem, status_code=201)
async def create_scenario_route(req: CreateScenarioRequest) -> BuilderScenarioItem:
    if not req.name.strip() or len(req.name) > 80:
        raise HTTPException(status_code=422, detail="invalid folder")
    if req.locale not in ("en", "pt-br"):
        raise HTTPException(status_code=422, detail="invalid folder")
    target = _resolve_target(req.folder)
    if target.exists():
        raise HTTPException(status_code=409, detail="folder exists")

    tmp_dir = target.parent / f".{req.folder}.tmp-{uuid.uuid4().hex}"
    try:
        _write_skeleton(tmp_dir, req.name, req.locale)
        os.replace(tmp_dir, target)
    except OSError as exc:
        emit("builder_scenario_write_failed", op="create", scenario_id=req.folder, error=str(exc))
        raise HTTPException(status_code=500, detail="write failed") from None
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    emit("builder_scenario_created", scenario_id=req.folder, locale=req.locale)
    return scan_one(req.folder)


@router.post("/scenarios/{scenario_id}/duplicate", response_model=BuilderScenarioItem, status_code=201)
async def duplicate_scenario_route(scenario_id: str, req: DuplicateScenarioRequest) -> BuilderScenarioItem:
    source = _resolve_source(scenario_id)
    target = _resolve_target(req.folder)
    if target.exists():
        raise HTTPException(status_code=409, detail="folder exists")

    tmp_dir = target.parent / f".{req.folder}.tmp-{uuid.uuid4().hex}"
    try:
        shutil.copytree(source, tmp_dir, dirs_exist_ok=False)
        os.replace(tmp_dir, target)
    except OSError as exc:
        emit("builder_scenario_write_failed", op="duplicate", scenario_id=req.folder, error=str(exc))
        raise HTTPException(status_code=500, detail="write failed") from None
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    emit("builder_scenario_duplicated", source_id=scenario_id, scenario_id=req.folder)
    return scan_one(req.folder)


@router.delete("/scenarios/{scenario_id}", status_code=204)
async def delete_scenario_route(scenario_id: str) -> None:
    target = _resolve_source(scenario_id)
    try:
        shutil.rmtree(target)
    except OSError as exc:
        emit("builder_scenario_write_failed", op="delete", scenario_id=scenario_id, error=str(exc))
        raise HTTPException(status_code=500, detail="delete failed") from None
    emit("builder_scenario_deleted", scenario_id=scenario_id)
