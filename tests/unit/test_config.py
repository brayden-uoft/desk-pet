from pathlib import Path

import pytest

from desk_pet.config import ConfigError, load_config


def test_loads_windows_configuration() -> None:
    config = load_config(Path("configs/windows.yaml"))

    assert config.profile == "windows"
    assert config.trigger.driver == "keyboard"
    assert config.trigger.listen_key == "right_alt"
    assert config.face.driver == "desktop_preview"
    assert config.audio.speech_speed == 1.5
    assert config.audio.thinking_audio_enabled


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
audio:
  input_driver: system_default
  output_driver: system_default
  input_device: null
  output_device: null
  sample_rate_hz: 16000
  block_duration_ms: 30
  silence_timeout_ms: 1200
  maximum_recording_seconds: 15
  silence_threshold: 500
  transcription_model: test-transcription
  speech_model: test-speech
  voice: test-voice
  speech_speed: 1.5
  thinking_audio_enabled: true
  thinking_phrase: Testing my circuits.
camera:
  driver: opencv
  index: 0
  maximum_dimension: 1024
  jpeg_quality: 80
  image_detail: auto
agent:
  provider: openai
  model: ${MODEL:-test-model}
  reasoning_effort: low
  request_timeout_seconds: 10
  maximum_output_tokens: 100
  history_limit: 5
  maximum_tool_iterations: 5
  web_search_enabled: true
  web_search_context_size: low
context:
  persona_path: configs/persona.md
  user_profile_path: data/private/user-profile.md
  maximum_characters: 20000
storage:
  database_path: data/test.db
""",
        encoding="utf-8",
    )

    assert load_config(path).profile == "test"


def test_invalid_web_search_configuration_is_rejected(tmp_path: Path) -> None:
    text = Path("configs/windows.yaml").read_text(encoding="utf-8")
    path = tmp_path / "config.yaml"
    path.write_text(
        text.replace("web_search_context_size: low", "web_search_context_size: enormous"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="web_search_context_size"):
        load_config(path)


def test_missing_required_value_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    path.write_text(
        (
            "profile: test\ntrigger: {}\nface: {}\naudio: {}\ncamera: {}\n"
            "agent: {}\ncontext: {}\nstorage: {}\n"
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="trigger.driver"):
        load_config(path)
