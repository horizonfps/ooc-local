import pytest
from pydantic import ValidationError

from app.config import DEFAULT_CONFIG, load_config


def test_creates_default_config_when_missing(tmp_path):
    path = tmp_path / "config.yaml"
    config = load_config(path)
    assert path.read_text(encoding="utf-8") == DEFAULT_CONFIG
    assert config.language == "pt-br"
    assert config.models["narrator"].provider == "local"


def test_rejects_role_with_unknown_provider(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n"
        "  local: {base_url: http://x/v1}\n"
        "models:\n"
        "  narrator: {provider: ghost, model: m}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="unknown provider"):
        load_config(path)
