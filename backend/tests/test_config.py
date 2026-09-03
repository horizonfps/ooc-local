import pytest
from pydantic import ValidationError

from app.config import DEFAULT_CONFIG, ProfileModel, load_config


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


def _base_yaml() -> str:
    return (
        "providers:\n"
        "  local: {base_url: http://x/v1}\n"
        "models:\n"
        "  narrator: {provider: local, model: m}\n"
    )


def test_profile_from_yaml_populates_profile_model(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        _base_yaml()
        + "profiles:\n"
        "  recommended:\n"
        "    narrator:\n"
        "      hf_repo: some/repo\n"
        "      file: model.gguf\n"
        "      port: 5101\n"
        "      ctx: 16384\n"
        "      gpu_layers: 20\n",
        encoding="utf-8",
    )
    config = load_config(path)
    model = config.profiles["recommended"]["narrator"]
    assert model.hf_repo == "some/repo"
    assert model.file == "model.gguf"
    assert model.port == 5101
    assert model.ctx == 16384
    assert model.gpu_layers == 20


def test_profile_model_defaults_ctx_and_gpu_layers(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        _base_yaml()
        + "profiles:\n"
        "  recommended:\n"
        "    narrator:\n"
        "      hf_repo: some/repo\n"
        "      file: model.gguf\n"
        "      port: 5101\n",
        encoding="utf-8",
    )
    config = load_config(path)
    model = config.profiles["recommended"]["narrator"]
    assert model.ctx == 8192
    assert model.gpu_layers == -1


def test_config_without_profiles_resolves_to_empty_dict(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(_base_yaml(), encoding="utf-8")
    config = load_config(path)
    assert config.profiles == {}


def test_profile_model_without_file_raises_validation_error():
    with pytest.raises(ValidationError):
        ProfileModel(hf_repo="some/repo", port=5101)
