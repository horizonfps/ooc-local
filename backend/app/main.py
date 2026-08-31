import json
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import load_config
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider
from app.observability import emit, setup_logging

SMOKE_SYSTEM_PROMPT = "You are the narrator of an interactive story. Reply briefly, in character."

app = FastAPI(title="ooc-local")
setup_logging()


class ChatRequest(BaseModel):
    message: str


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


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
