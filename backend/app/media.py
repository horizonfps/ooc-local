from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.observability import emit
from app.scenario import LoadedScenario, ScenarioError, scenario_path

router = APIRouter()

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_EXTENSIONS: tuple[str, ...] = ("png", "jpg", "webp")
KEY_RE = re.compile(r"^[a-z0-9-]+$")
_FILE_RE = re.compile(r"^([a-z0-9-]+)\.(png|jpg|webp)$")


class MediaIndex(BaseModel):
    cover: str | None = None
    sprites: dict[str, dict[str, str]] = {}
    backgrounds: dict[str, str] = {}


class SessionAssets(BaseModel):
    sprites: dict[str, dict[str, str]] = {}
    backgrounds: dict[str, str] = {}


def media_root(scenario_id: str) -> Path:
    return scenario_path(scenario_id) / "media"


def media_url(scenario_id: str, relative: str) -> str:
    return f"/api/scenarios/{scenario_id}/media/{relative}"


def _scan_flat(directory: Path) -> dict[str, str]:
    """Maps stem -> filename, resolving space collisions by extension priority."""
    if not directory.is_dir():
        return {}
    found: dict[str, dict[str, str]] = {}
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        match = _FILE_RE.match(entry.name)
        if not match:
            continue
        stem, ext = match.group(1), match.group(2)
        found.setdefault(stem, {})[ext] = entry.name

    resolved: dict[str, str] = {}
    for stem, by_ext in found.items():
        for ext in ALLOWED_EXTENSIONS:
            if ext in by_ext:
                resolved[stem] = by_ext[ext]
                break
    return resolved


def scan_media(scenario_id: str) -> MediaIndex:
    root = media_root(scenario_id)
    if not root.is_dir():
        return MediaIndex(cover=None, sprites={}, backgrounds={})

    cover = None
    for ext in ALLOWED_EXTENSIONS:
        candidate = root / f"cover.{ext}"
        if candidate.is_file():
            cover = media_url(scenario_id, f"cover.{ext}")
            break

    sprites: dict[str, dict[str, str]] = {}
    sprites_dir = root / "sprites"
    if sprites_dir.is_dir():
        for folder in sorted(sprites_dir.iterdir()):
            if not folder.is_dir() or not KEY_RE.match(folder.name):
                continue
            flat = _scan_flat(folder)
            if flat:
                sprites[folder.name] = {
                    emotion: media_url(scenario_id, f"sprites/{folder.name}/{filename}")
                    for emotion, filename in flat.items()
                }

    backgrounds = {
        location: media_url(scenario_id, f"backgrounds/{filename}")
        for location, filename in _scan_flat(root / "backgrounds").items()
    }

    emit(
        "media_scanned",
        scenario_id=scenario_id,
        sprite_folders=len(sprites),
        sprite_files=sum(len(emotions) for emotions in sprites.values()),
        backgrounds=len(backgrounds),
        has_cover=cover is not None,
    )
    return MediaIndex(cover=cover, sprites=sprites, backgrounds=backgrounds)


def session_assets(scenario: LoadedScenario) -> SessionAssets:
    root = media_root(scenario.id)
    sprites_dir = root / "sprites"

    sprites: dict[str, dict[str, str]] = {}
    for char_id, character in scenario.characters.items():
        folder_name = character.sprite or char_id
        flat = _scan_flat(sprites_dir / folder_name)
        if not flat:
            continue
        urls = {
            emotion: media_url(scenario.id, f"sprites/{folder_name}/{filename}")
            for emotion, filename in flat.items()
        }
        sprites[char_id.lower()] = urls
        if character.sprite and character.sprite.lower() != char_id.lower():
            sprites[character.sprite.lower()] = urls

    backgrounds = {
        location.lower(): media_url(scenario.id, f"backgrounds/{filename}")
        for location, filename in _scan_flat(root / "backgrounds").items()
    }

    return SessionAssets(sprites=sprites, backgrounds=backgrounds)


def _require_scenario(scenario_id: str) -> Path:
    try:
        path = scenario_path(scenario_id)
    except ScenarioError:
        raise HTTPException(status_code=404, detail="scenario not found") from None
    if not path.is_dir() or not (path / "scenario.yaml").exists():
        raise HTTPException(status_code=404, detail="scenario not found")
    return path


@router.get("/api/builder/scenarios/{scenario_id}/media", response_model=MediaIndex)
async def get_media_index_route(scenario_id: str) -> MediaIndex:
    _require_scenario(scenario_id)
    return scan_media(scenario_id)


@router.get("/api/scenarios/{scenario_id}/media/{path:path}")
async def get_media_file_route(scenario_id: str, path: str) -> FileResponse:
    extension = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if extension not in ("png", "jpg", "jpeg", "webp"):
        emit("media_forbidden", scenario_id=scenario_id, path=path)
        raise HTTPException(status_code=404, detail="not found")

    try:
        root = media_root(scenario_id)
    except ScenarioError:
        emit("media_forbidden", scenario_id=scenario_id, path=path)
        raise HTTPException(status_code=404, detail="not found") from None

    candidate = (root / path).resolve()
    if root.resolve() not in candidate.parents:
        emit("media_forbidden", scenario_id=scenario_id, path=path)
        raise HTTPException(status_code=404, detail="not found")

    if not candidate.is_file():
        emit("media_forbidden", scenario_id=scenario_id, path=path)
        raise HTTPException(status_code=404, detail="not found")

    return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
