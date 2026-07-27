import pytest

from desk_pet.config import ConfigError, load_config
from desk_pet.main import build_application


def test_build_application_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    config = load_config("configs/windows.yaml")

    with pytest.raises(ConfigError, match="OPENAI_API_KEY is missing"):
        build_application(config)
