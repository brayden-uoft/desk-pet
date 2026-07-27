from pathlib import Path

import pytest

from desk_pet.config import ConfigError, load_config


def test_loads_windows_configuration() -> None:
    config = load_config(Path("configs/windows.yaml"))

    assert config.profile == "windows"
    assert config.trigger.driver == "keyboard"
    assert config.trigger.listen_key == "space"
    assert config.face.driver == "terminal"


def test_environment_default_is_expanded(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        """
profile: ${PROFILE:-test}
trigger:
  driver: keyboard
  listen_key: space
  cancel_key: escape
face:
  driver: terminal
agent:
  provider: openai
  model: ${MODEL:-test-model}
  reasoning_effort: low
  request_timeout_seconds: 10
  maximum_output_tokens: 100
  history_limit: 5
  maximum_tool_iterations: 5
storage:
  database_path: data/test.db
""",
        encoding="utf-8",
    )

    assert load_config(path).profile == "test"


def test_missing_required_value_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        "profile: test\ntrigger: {}\nface: {}\nagent: {}\nstorage: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="trigger.driver"):
        load_config(path)
