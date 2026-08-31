import json

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import load_config
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider

SMOKE_SYSTEM_PROMPT = "You are the narrator of an interactive story. Reply briefly, in character."

app = FastAPI(title="ooc-local")


class ChatRequest(BaseModel):
    message: str


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    config = load_config()
    role = config.models["narrator"]
    provider = OpenAICompatProvider(config.providers[role.provider])
    messages = [
        ChatMessage(role="system", content=SMOKE_SYSTEM_PROMPT),
        ChatMessage(role="user", content=req.message),
    ]

    async def event_stream():
        try:
            async for delta in provider.stream_chat(messages, role.model):
                yield f"data: {json.dumps({'delta': delta})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
