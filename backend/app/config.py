import os
from pathlib import Path

import yaml
from pydantic import BaseModel, model_validator

CONFIG_DIR = Path.home() / ".ooc-local"
CONFIG_PATH = CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG = """\
language: pt-br
providers:
  local:
    base_url: http://127.0.0.1:5001/v1
    api_key_env: OOC_LOCAL_API_KEY
models:
  narrator: {provider: local, model: Cydonia-24B-v4.3}
  utility:  {provider: local, model: Cydonia-24B-v4.3}
  builder:  {provider: local, model: Cydonia-24B-v4.3}
"""


class ProviderConfig(BaseModel):
    base_url: str
    api_key_env: str = "OOC_LOCAL_API_KEY"

    @property
    def api_key(self) -> str:
        return os.environ.get(self.api_key_env, "none")


class ModelRole(BaseModel):
    provider: str
    model: str


class Config(BaseModel):
    language: str = "pt-br"
    providers: dict[str, ProviderConfig]
    models: dict[str, ModelRole]

    @model_validator(mode="after")
    def roles_reference_known_providers(self) -> "Config":
        for role, ref in self.models.items():
            if ref.provider not in self.providers:
                raise ValueError(f"model role '{role}' references unknown provider '{ref.provider}'")
        return self


def load_config(path: Path = CONFIG_PATH) -> Config:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Config.model_validate(data)
