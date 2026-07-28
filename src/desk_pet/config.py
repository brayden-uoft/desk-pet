from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}]*))?\}")


@dataclass(frozen=True, slots=True)
class TriggerConfig:
    driver: str
    listen_key: str
    cancel_key: str


@dataclass(frozen=True, slots=True)
class FaceConfig:
    driver: str


@dataclass(frozen=True, slots=True)
class AudioConfig:
    input_driver: str
    output_driver: str
    input_device: str | int | None
    output_device: str | int | None
    sample_rate_hz: int
    block_duration_ms: int
    silence_timeout_ms: int
    maximum_recording_seconds: float
    silence_threshold: float
    transcription_model: str
    speech_model: str
    voice: str
    speech_speed: float
    thinking_audio_enabled: bool
    thinking_volume: float
    thinking_clip_seconds: float


@dataclass(frozen=True, slots=True)
class CameraConfig:
    driver: str
    index: int
    maximum_dimension: int
    jpeg_quality: int
    image_detail: Literal["low", "high", "auto"]


@dataclass(frozen=True, slots=True)
class AgentConfig:
    provider: str
    model: str
    reasoning_effort: str
    request_timeout_seconds: float
    maximum_output_tokens: int
    history_limit: int
    maximum_tool_iterations: int
    web_search_enabled: bool
    web_search_context_size: Literal["low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class StorageConfig:
    database_path: Path


@dataclass(frozen=True, slots=True)
class ContextConfig:
    persona_path: Path
    user_profile_path: Path
    maximum_characters: int


@dataclass(frozen=True, slots=True)
class AppConfig:
    profile: str
    trigger: TriggerConfig
    face: FaceConfig
    audio: AudioConfig
    camera: CameraConfig
    agent: AgentConfig
    context: ContextConfig
    storage: StorageConfig


class ConfigError(ValueError):
    """Configuration is missing or invalid."""


def _expand_environment(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        name, default = match.group(1), match.group(2)
        value = os.getenv(name, default)
        if value is None:
            raise ConfigError(f"Environment variable {name} is required")
        return value

    return _ENV_PATTERN.sub(replace, text)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _required_string(mapping: dict[str, Any], key: str, section: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{section}.{key} must be a non-empty string")
    return value


def _positive_number(mapping: dict[str, Any], key: str, section: str) -> float:
    value = mapping.get(key)
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{section}.{key} must be a positive number")
    return float(value)


def _positive_integer(mapping: dict[str, Any], key: str, section: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{section}.{key} must be a positive integer")
    return value


def _required_boolean(mapping: dict[str, Any], key: str, section: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise ConfigError(f"{section}.{key} must be true or false")
    return value


def _web_search_context_size(
    mapping: dict[str, Any],
) -> Literal["low", "medium", "high"]:
    value = mapping.get("web_search_context_size")
    if value not in {"low", "medium", "high"}:
        raise ConfigError("agent.web_search_context_size must be low, medium, or high")
    return cast(Literal["low", "medium", "high"], value)


def _device_selector(mapping: dict[str, Any], key: str, section: str) -> str | int | None:
    value = mapping.get(key)
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    raise ConfigError(f"{section}.{key} must be null, a device name, or a non-negative index")


def _non_negative_integer(mapping: dict[str, Any], key: str, section: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{section}.{key} must be a non-negative integer")
    return value


def _bounded_integer(
    mapping: dict[str, Any],
    key: str,
    section: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ConfigError(f"{section}.{key} must be an integer from {minimum} to {maximum}")
    return value


def _bounded_number(
    mapping: dict[str, Any],
    key: str,
    section: str,
    *,
    minimum: float,
    maximum: float,
) -> float:
    value = mapping.get(key)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise ConfigError(f"{section}.{key} must be a number from {minimum} to {maximum}")
    return float(value)


def _image_detail(mapping: dict[str, Any]) -> Literal["low", "high", "auto"]:
    value = mapping.get("image_detail")
    if value not in {"low", "high", "auto"}:
        raise ConfigError("camera.image_detail must be low, high, or auto")
    return cast(Literal["low", "high", "auto"], value)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Could not read configuration: {config_path}") from exc

    try:
        raw = yaml.safe_load(_expand_environment(text))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}") from exc

    root = _mapping(raw, "configuration")
    trigger = _mapping(root.get("trigger"), "trigger")
    face = _mapping(root.get("face"), "face")
    audio = _mapping(root.get("audio"), "audio")
    camera = _mapping(root.get("camera"), "camera")
    agent = _mapping(root.get("agent"), "agent")
    context = _mapping(root.get("context"), "context")
    storage = _mapping(root.get("storage"), "storage")
    return AppConfig(
        profile=_required_string(root, "profile", "configuration"),
        trigger=TriggerConfig(
            driver=_required_string(trigger, "driver", "trigger"),
            listen_key=_required_string(trigger, "listen_key", "trigger"),
            cancel_key=_required_string(trigger, "cancel_key", "trigger"),
        ),
        face=FaceConfig(driver=_required_string(face, "driver", "face")),
        audio=AudioConfig(
            input_driver=_required_string(audio, "input_driver", "audio"),
            output_driver=_required_string(audio, "output_driver", "audio"),
            input_device=_device_selector(audio, "input_device", "audio"),
            output_device=_device_selector(audio, "output_device", "audio"),
            sample_rate_hz=_positive_integer(audio, "sample_rate_hz", "audio"),
            block_duration_ms=_positive_integer(audio, "block_duration_ms", "audio"),
            silence_timeout_ms=_positive_integer(audio, "silence_timeout_ms", "audio"),
            maximum_recording_seconds=_positive_number(
                audio,
                "maximum_recording_seconds",
                "audio",
            ),
            silence_threshold=_positive_number(audio, "silence_threshold", "audio"),
            transcription_model=_required_string(audio, "transcription_model", "audio"),
            speech_model=_required_string(audio, "speech_model", "audio"),
            voice=_required_string(audio, "voice", "audio"),
            speech_speed=_bounded_number(
                audio,
                "speech_speed",
                "audio",
                minimum=0.25,
                maximum=4.0,
            ),
            thinking_audio_enabled=_required_boolean(
                audio,
                "thinking_audio_enabled",
                "audio",
            ),
            thinking_volume=_bounded_number(
                audio,
                "thinking_volume",
                "audio",
                minimum=0.01,
                maximum=1.0,
            ),
            thinking_clip_seconds=_bounded_number(
                audio,
                "thinking_clip_seconds",
                "audio",
                minimum=1.0,
                maximum=10.0,
            ),
        ),
        camera=CameraConfig(
            driver=_required_string(camera, "driver", "camera"),
            index=_non_negative_integer(camera, "index", "camera"),
            maximum_dimension=_positive_integer(camera, "maximum_dimension", "camera"),
            jpeg_quality=_bounded_integer(
                camera,
                "jpeg_quality",
                "camera",
                minimum=1,
                maximum=100,
            ),
            image_detail=_image_detail(camera),
        ),
        agent=AgentConfig(
            provider=_required_string(agent, "provider", "agent"),
            model=_required_string(agent, "model", "agent"),
            reasoning_effort=_required_string(agent, "reasoning_effort", "agent"),
            request_timeout_seconds=_positive_number(agent, "request_timeout_seconds", "agent"),
            maximum_output_tokens=_positive_integer(agent, "maximum_output_tokens", "agent"),
            history_limit=_positive_integer(agent, "history_limit", "agent"),
            maximum_tool_iterations=_positive_integer(agent, "maximum_tool_iterations", "agent"),
            web_search_enabled=_required_boolean(agent, "web_search_enabled", "agent"),
            web_search_context_size=_web_search_context_size(agent),
        ),
        context=ContextConfig(
            persona_path=Path(_required_string(context, "persona_path", "context")),
            user_profile_path=Path(_required_string(context, "user_profile_path", "context")),
            maximum_characters=_positive_integer(
                context,
                "maximum_characters",
                "context",
            ),
        ),
        storage=StorageConfig(
            database_path=Path(_required_string(storage, "database_path", "storage"))
        ),
    )
