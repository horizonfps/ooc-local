from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.observability import emit
from app.scenario import LoadedScenario, ScenarioError, load_scenario, scenario_path
from app.sessions import ScenarioUnlock, read_scenario_unlocks

router = APIRouter()


class GalleryEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    rarity: str
    hint: str | None
    unlocked: bool
    unlocked_at: str | None = Field(alias="unlockedAt")
    session_id: str | None = Field(alias="sessionId")
    turn: int | None


class GalleryStart(BaseModel):
    id: str
    name: str
    achievements: list[GalleryEntry]
    endings: list[GalleryEntry]


class GalleryTotals(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    achievements: int
    achievements_unlocked: int = Field(alias="achievementsUnlocked")
    endings: int
    endings_unlocked: int = Field(alias="endingsUnlocked")


class Gallery(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scenario_id: str = Field(alias="scenarioId")
    scenario_name: str = Field(alias="scenarioName")
    starts: list[GalleryStart]
    totals: GalleryTotals


def build_gallery(scenario: LoadedScenario, unlocks: list[ScenarioUnlock]) -> Gallery:
    by_start: dict[str, dict[str, ScenarioUnlock]] = {}
    orphans = 0
    declared_by_start: dict[str, set[str]] = {
        start_id: {achievement.id for achievement in start.achievements}
        for start_id, start in scenario.starts.items()
    }
    for unlock in unlocks:
        declared = declared_by_start.get(unlock.start_id)
        if declared is None or unlock.id not in declared:
            orphans += 1
            continue
        first_by_id = by_start.setdefault(unlock.start_id, {})
        current = first_by_id.get(unlock.id)
        if current is None or unlock.created_at < current.created_at:
            first_by_id[unlock.id] = unlock

    starts: list[GalleryStart] = []
    total_achievements = 0
    total_achievements_unlocked = 0
    total_endings = 0
    total_endings_unlocked = 0

    for start_id, start in scenario.starts.items():
        first_by_id = by_start.get(start_id, {})
        achievements: list[GalleryEntry] = []
        endings: list[GalleryEntry] = []
        for declared in start.achievements:
            unlock = first_by_id.get(declared.id)
            entry = GalleryEntry(
                id=declared.id,
                name=declared.name,
                rarity=declared.rarity,
                hint=declared.hint,
                unlocked=unlock is not None,
                unlocked_at=unlock.created_at if unlock else None,
                session_id=unlock.session_id if unlock else None,
                turn=unlock.turn if unlock else None,
            )
            if declared.type == "achievement":
                achievements.append(entry)
            else:
                endings.append(entry)
        starts.append(GalleryStart(id=start.id, name=start.name, achievements=achievements, endings=endings))
        total_achievements += len(achievements)
        total_achievements_unlocked += sum(1 for entry in achievements if entry.unlocked)
        total_endings += len(endings)
        total_endings_unlocked += sum(1 for entry in endings if entry.unlocked)

    emit(
        "gallery_read",
        scenario_id=scenario.id,
        starts=len(starts),
        declared=total_achievements + total_endings,
        unlocked=total_achievements_unlocked + total_endings_unlocked,
        orphans=orphans,
    )

    return Gallery(
        scenario_id=scenario.id,
        scenario_name=scenario.meta.name,
        starts=starts,
        totals=GalleryTotals(
            achievements=total_achievements,
            achievements_unlocked=total_achievements_unlocked,
            endings=total_endings,
            endings_unlocked=total_endings_unlocked,
        ),
    )


@router.get("/api/scenarios/{scenario_id}/gallery", response_model=Gallery)
async def get_scenario_gallery_route(scenario_id: str) -> Gallery:
    try:
        scenario_path(scenario_id)
    except ScenarioError:
        raise HTTPException(status_code=422, detail="invalid folder") from None
    try:
        scenario = load_scenario(scenario_id)
    except ScenarioError:
        raise HTTPException(status_code=404, detail="scenario not found") from None

    unlocks = read_scenario_unlocks(scenario_id)
    return build_gallery(scenario, unlocks)
