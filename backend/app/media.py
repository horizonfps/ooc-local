from __future__ import annotations

import os
import re
import tempfile
from contextlib import suppress
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import load_config
from app.observability import emit
from app.scenario import LoadedScenario, ScenarioError, scenario_path

router = APIRouter()

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
UPLOAD_CHUNK_BYTES = 64 * 1024
ALLOWED_EXTENSIONS: tuple[str, ...] = ("png", "jpg", "webp")
MEDIA_KINDS: tuple[str, ...] = ("cover", "sprite", "background")
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
        if not KEY_RE.match(folder_name):
            continue
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


def _detect_extension(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header[0:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    return None


def _space_dir(scenario_id: str, kind: str, character: str | None) -> Path:
    root = media_root(scenario_id)
    if kind == "sprite":
        return root / "sprites" / (character or "")
    if kind == "background":
        return root / "backgrounds"
    return root


def _relative_path(kind: str, key: str, character: str | None, ext: str) -> str:
    if kind == "sprite":
        return f"sprites/{character}/{key}.{ext}"
    if kind == "background":
        return f"backgrounds/{key}.{ext}"
    return f"cover.{ext}"


def _validate_media_target(scenario_id: str, kind: str, key: str, character: str | None) -> str:
    """Validates kind/character shape and the resolved key, returns the effective key."""
    character = character or None
    if kind not in MEDIA_KINDS:
        raise HTTPException(status_code=422, detail="invalid kind")
    if kind == "sprite" and not character:
        raise HTTPException(status_code=422, detail="character required for sprite")
    if kind == "background" and character:
        raise HTTPException(status_code=422, detail="character forbidden for background")

    effective_key = "cover" if kind == "cover" else key
    if not KEY_RE.match(effective_key) or (character is not None and not KEY_RE.match(character)):
        emit("media_rejected", scenario_id=scenario_id, kind=kind, reason="key")
        raise HTTPException(status_code=422, detail="invalid key")
    return effective_key


@router.post("/api/builder/scenarios/{scenario_id}/media", status_code=201)
async def post_media_route(
    scenario_id: str,
    kind: str = Form(...),
    key: str = Form(""),
    character: str | None = Form(None),
    file: UploadFile = File(...),
) -> dict[str, str]:
    config = load_config()
    if not config.flag("builder"):
        emit("builder_rejected", scenario_id=scenario_id, reason="builder disabled by flag")
        raise HTTPException(status_code=503, detail="builder disabled by flag")

    _require_scenario(scenario_id)
    effective_key = _validate_media_target(scenario_id, kind, key, character)

    data = bytearray()
    while True:
        chunk = await file.read(UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > MAX_UPLOAD_BYTES:
            emit("media_rejected", scenario_id=scenario_id, kind=kind, reason="size")
            raise HTTPException(status_code=413, detail="file too large")

    ext = _detect_extension(bytes(data[:16]))
    if ext is None:
        emit("media_rejected", scenario_id=scenario_id, kind=kind, reason="type")
        raise HTTPException(status_code=415, detail="unsupported media type")

    space_dir = _space_dir(scenario_id, kind, character)
    target = space_dir / f"{effective_key}.{ext}"
    try:
        space_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=space_dir)
        try:
            with os.fdopen(fd, "wb") as tmp_file:
                tmp_file.write(data)
            os.replace(tmp_name, target)
        except OSError:
            with suppress(OSError):
                os.remove(tmp_name)
            raise
        for other_ext in ALLOWED_EXTENSIONS:
            if other_ext == ext:
                continue
            sibling = space_dir / f"{effective_key}.{other_ext}"
            if sibling.exists():
                sibling.unlink()
    except OSError as exc:
        emit("media_write_failed", scenario_id=scenario_id, path=str(target), error=str(exc))
        raise HTTPException(status_code=500, detail="write failed") from None

    relative = _relative_path(kind, effective_key, character, ext)
    emit("media_uploaded", scenario_id=scenario_id, kind=kind, key=effective_key, bytes=len(data), ext=ext)
    return {"path": relative, "url": media_url(scenario_id, relative)}


@router.delete("/api/builder/scenarios/{scenario_id}/media", status_code=204)
async def delete_media_route(
    scenario_id: str,
    kind: str,
    key: str = "",
    character: str | None = None,
) -> Response:
    config = load_config()
    if not config.flag("builder"):
        emit("builder_rejected", scenario_id=scenario_id, reason="builder disabled by flag")
        raise HTTPException(status_code=503, detail="builder disabled by flag")

    _require_scenario(scenario_id)
    effective_key = _validate_media_target(scenario_id, kind, key, character)

    space_dir = _space_dir(scenario_id, kind, character)
    removed = False
    try:
        for ext in ALLOWED_EXTENSIONS:
            candidate = space_dir / f"{effective_key}.{ext}"
            if candidate.exists():
                candidate.unlink()
                removed = True
    except OSError as exc:
        emit("media_write_failed", scenario_id=scenario_id, path=str(space_dir), error=str(exc))
        raise HTTPException(status_code=500, detail="delete failed") from None

    if not removed:
        raise HTTPException(status_code=404, detail="asset not found")

    emit("media_removed", scenario_id=scenario_id, kind=kind, key=effective_key)
    return Response(status_code=204)
