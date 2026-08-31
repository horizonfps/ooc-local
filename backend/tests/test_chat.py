from fastapi.testclient import TestClient

from app import main
from app.llm.openai_compat import OpenAICompatProvider


async def fake_stream(self, messages, model):
    for delta in ["olá", " mundo"]:
        yield delta


def test_chat_streams_sse(monkeypatch, tmp_path):
    monkeypatch.setattr(OpenAICompatProvider, "stream_chat", fake_stream)
    monkeypatch.setattr(main, "load_config", lambda: _fake_config())
    client = TestClient(main.app)
    with client.stream("POST", "/api/chat", json={"message": "oi"}) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(response.iter_text())
    assert '{"delta": "ol\\u00e1"}' in body or '"olá"' in body
    assert body.strip().endswith("data: [DONE]")


def _fake_config():
    from app.config import Config

    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
        }
    )


def test_health():
    client = TestClient(main.app)
    assert client.get("/api/health").json() == {"status": "ok"}
