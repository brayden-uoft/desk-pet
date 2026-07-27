from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
class AgentConfig:
    provider: str
    model: str
    reasoning_effort: str
    request_timeout_seconds: float
    maximum_output_tokens: int
    history_limit: int


@dataclass(frozen=True, slots=True)
class StorageConfig:
    database_path: Path


@dataclass(frozen=True, slots=True)
class AppConfig:
    profile: str
    trigger: TriggerConfig
    face: FaceConfig
    agent: AgentConfig
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
    agent = _mapping(root.get("agent"), "agent")
    storage = _mapping(root.get("storage"), "storage")
    return AppConfig(
        profile=_required_string(root, "profile", "configuration"),
        trigger=TriggerConfig(
            driver=_required_string(trigger, "driver", "trigger"),
            listen_key=_required_string(trigger, "listen_key", "trigger"),
            cancel_key=_required_string(trigger, "cancel_key", "trigger"),
        ),
        face=FaceConfig(driver=_required_string(face, "driver", "face")),
        agent=AgentConfig(
            provider=_required_string(agent, "provider", "agent"),
            model=_required_string(agent, "model", "agent"),
            reasoning_effort=_required_string(agent, "reasoning_effort", "agent"),
            request_timeout_seconds=_positive_number(agent, "request_timeout_seconds", "agent"),
            maximum_output_tokens=_positive_integer(agent, "maximum_output_tokens", "agent"),
            history_limit=_positive_integer(agent, "history_limit", "agent"),
        ),
        storage=StorageConfig(
            database_path=Path(_required_string(storage, "database_path", "storage"))
        ),
    )
