import json
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.config import load_config
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
from app.observability import emit, setup_logging
from app.scenario import list_scenarios
from app.sessions import (
    ScenarioNotFound,
    SessionDetail,
    SessionNotFound,
    SessionSummary,
    StartNotFound,
    create_session,
    get_session,
    list_sessions,
)
from app.turn import run_turn

SMOKE_SYSTEM_PROMPT = "You are the narrator of an interactive story. Reply briefly, in character."

app = FastAPI(title="ooc-local")
setup_logging()


class ChatRequest(BaseModel):
    message: str


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    scenario_id: str = Field(alias="scenarioId")
    start_id: str | None = Field(default=None, alias="startId")


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/scenarios")
async def scenarios() -> list[dict[str, str | None]]:
    return [
        {
            "id": scenario.id,
            "name": scenario.meta.name,
            "tagline": scenario.meta.tagline,
            "locale": scenario.meta.locale,
        }
        for scenario in list_scenarios()
    ]


@app.post("/api/sessions", response_model=SessionDetail, status_code=201)
async def create_session_route(req: CreateSessionRequest) -> SessionDetail:
    try:
        return create_session(req.scenario_id, req.start_id)
    except ScenarioNotFound:
        raise HTTPException(status_code=404, detail="scenario not found") from None
    except StartNotFound:
        raise HTTPException(status_code=404, detail="start not found") from None


@app.get("/api/sessions", response_model=list[SessionSummary])
async def list_sessions_route() -> list[SessionSummary]:
    return list_sessions()


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
async def get_session_route(session_id: str) -> SessionDetail:
    try:
        return get_session(session_id)
    except SessionNotFound:
        raise HTTPException(status_code=404, detail="session not found") from None
    except ScenarioNotFound:
        raise HTTPException(status_code=404, detail="scenario not found") from None


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    config = load_config()
    if not config.flag("chat"):
        raise HTTPException(status_code=503, detail="chat disabled by flag")
    role = config.models["narrator"]
    provider = OpenAICompatProvider(config.providers[role.provider])
    messages = [
        ChatMessage(role="system", content=SMOKE_SYSTEM_PROMPT),
        ChatMessage(role="user", content=req.message),
    ]

    async def event_stream():
        started = time.monotonic()
        chars = 0
        error = None
        try:
            async for delta in provider.stream_chat(messages, role.model):
                chars += len(delta)
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except Exception as exc:
            error = str(exc)
            yield f"data: {json.dumps({'error': error})}\n\n"
        yield "data: [DONE]\n\n"
        emit(
            "chat_turn",
            model=role.model,
            duration_ms=int((time.monotonic() - started) * 1000),
            chars=chars,
            error=error,
        )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.post("/api/sessions/{session_id}/turn")
async def turn_route(session_id: str, req: ChatRequest) -> StreamingResponse:
    config = load_config()
    if not config.flag("chat"):
        emit("turn_rejected", session_id=session_id, reason="chat disabled by flag")
        raise HTTPException(status_code=503, detail="chat disabled by flag")
    if not req.message.strip():
        emit("turn_rejected", session_id=session_id, reason="message must not be empty")
        raise HTTPException(status_code=422, detail="message must not be empty")
    try:
        get_session(session_id)
    except SessionNotFound:
        emit("turn_rejected", session_id=session_id, reason="session not found")
        raise HTTPException(status_code=404, detail="session not found") from None
    except ScenarioNotFound:
        emit("turn_rejected", session_id=session_id, reason="scenario not found")
        raise HTTPException(status_code=404, detail="scenario not found") from None

    async def event_stream():
        async for event in run_turn(session_id, req.message):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
