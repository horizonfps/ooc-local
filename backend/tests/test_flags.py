from fastapi.testclient import TestClient

from app import main
from app.config import Config


def _config(flags: dict[str, bool]) -> Config:
    return Config.model_validate(
        {
            "providers": {"local": {"base_url": "http://x/v1"}},
            "models": {"narrator": {"provider": "local", "model": "m"}},
            "flags": flags,
        }
    )


def test_flag_defaults_to_on():
    assert _config({}).flag("chat") is True


def test_chat_disabled_by_flag(monkeypatch):
    monkeypatch.setattr(main, "load_config", lambda: _config({"chat": False}))
    client = TestClient(main.app)
    response = client.post("/api/chat", json={"message": "oi"})
    assert response.status_code == 503
