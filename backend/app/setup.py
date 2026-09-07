from __future__ import annotations

import re

from pydantic import BaseModel

from app.config import load_config
from app.observability import emit
from app.scenario import LoadedScenario, SETUP_ANSWER_CHARS, StartConfig

BUILTIN_VARIABLES = ("player", "start", "scenario")
SETUP_EVENT_KIND = "setup"
_VAR_RE = re.compile(r"\{\{\s*([a-z0-9_-]+)\s*\}\}")

_INTERPOLATED_FIELDS = ("world", "prologue", "opening_scene", "conflict", "mission")


class SetupAnswers(BaseModel):
    answers: dict[str, str] = {}
    free: bool = False


class SetupInvalid(Exception):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


def resolve_answers(start: StartConfig, raw: dict[str, str] | None) -> dict[str, str]:
    """Validates and completes raw answers with defaults. Unknown keys are
    dropped silently; missing or invalid answers raise SetupInvalid."""
    raw = raw or {}
    resolved: dict[str, str] = {}
    errors: list[str] = []
    for question in start.setup:
        value = raw.get(question.id)
        if value is None:
            if question.default is None:
                errors.append(question.id)
                emit(
                    "setup_rejected",
                    start_id=start.id,
                    reason="missing_answer",
                    question_id=question.id,
                )
                continue
            value = question.default
        if len(value) > SETUP_ANSWER_CHARS:
            errors.append(question.id)
            emit(
                "setup_rejected",
                start_id=start.id,
                reason="too_long",
                question_id=question.id,
            )
            continue
        if question.type == "choice" and value not in question.options:
            errors.append(question.id)
            emit(
                "setup_rejected",
                start_id=start.id,
                reason="invalid_choice",
                question_id=question.id,
            )
            continue
        resolved[question.id] = value
    if errors:
        raise SetupInvalid(errors)
    return resolved


def render(text: str, values: dict[str, str]) -> tuple[str, list[str]]:
    """Substitutes {{var}} occurrences. Unknown variables become empty
    strings; {{ without a closing }} is left literal."""
    unknown: list[str] = []

    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in values:
            return values[name]
        unknown.append(name)
        return ""

    rendered = _VAR_RE.sub(_replace, text)
    return rendered, unknown


def apply_setup(
    scenario: LoadedScenario, start: StartConfig, answers: SetupAnswers
) -> tuple[LoadedScenario, StartConfig]:
    """Returns copies of scenario and start with {{var}} interpolated in world,
    prologue, opening_scene, conflict, mission and lorebook entry bodies."""
    config = load_config()
    if not config.flag("setup"):
        return scenario, start

    values = dict(answers.answers)
    values.setdefault("start", start.name)
    values.setdefault("scenario", scenario.meta.name)
    values.setdefault("player", answers.answers.get("player", ""))

    unknown_total: list[str] = []
    fields_changed = 0

    def _apply_field(session_field: str, text: str | None) -> str | None:
        nonlocal fields_changed
        if text is None:
            return None
        rendered, unknown = render(text, values)
        for name in unknown:
            emit("setup_unknown_variable", field=session_field, name=name)
        unknown_total.extend(unknown)
        if rendered != text:
            fields_changed += 1
        return rendered

    new_world = _apply_field("world", scenario.world)
    start_updates = {}
    for field in ("prologue", "opening_scene", "conflict", "mission"):
        start_updates[field] = _apply_field(field, getattr(start, field))

    new_lorebook = {}
    for entry_id, entry in scenario.lorebook.items():
        new_body = _apply_field(f"lorebook.{entry_id}.body", entry.body)
        new_lorebook[entry_id] = entry.model_copy(update={"body": new_body})

    new_start = start.model_copy(update=start_updates)
    new_scenario = scenario.model_copy(update={"world": new_world, "lorebook": new_lorebook})

    emit(
        "setup_applied",
        fields=fields_changed,
        substitutions=len(values),
    )
    return new_scenario, new_start


def setup_event(answers: SetupAnswers) -> tuple[str, dict]:
    return SETUP_EVENT_KIND, answers.model_dump()


def read_setup(session_id: str) -> SetupAnswers:
    """Last setup event's answers, or empty answers if the session never had
    one. A malformed payload is treated as absence, never raised."""
    from app.sessions import read_events

    events = read_events(session_id, kinds=(SETUP_EVENT_KIND,))
    if not events:
        return SetupAnswers()
    payload = events[-1].payload
    try:
        return SetupAnswers.model_validate(payload)
    except Exception:
        return SetupAnswers()
